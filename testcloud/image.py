# -*- coding: utf-8 -*-
# Copyright 2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""
Representation of a cloud image which can be used to boot instances
"""

import sys
import os
import subprocess
import re
import shutil
import logging
import peewee
import requests
import random
import time
from urllib.parse import urlparse

from testcloud import config
from testcloud.exceptions import TestcloudImageError, TestcloudPermissionsError
from testcloud.sql import DB, DBImage, utcnow

config_data = config.get_config()

log = logging.getLogger("testcloud.image")


def list_images():
    """List the images currently downloaded and available on the system

    :returns: list of images currently available
    """

    image_dir = config_data.STORE_DIR
    images = [i for i in os.listdir(image_dir) if not i.endswith(".part")]

    return images


def find_image(name, uri=None):
    """Find an image matching a given name and optionally, a uri

    :param name: name of the image to look for
    :param uri: source uri to use if the image is found

    :returns: :py:class:`Image` if an image is found, otherwise None
    """
    images = list_images()

    if uri is not None:
        log.warning("find_image - uri parameter is deprecated and ignored")

    if name in images:
        uri = "file://{}/{}".format(config_data.STORE_DIR, name)
        return Image(uri)
    else:
        return None


class Image(object):
    """Handles base cloud images and prepares them for boot. This includes
    downloading images from remote systems (http, https supported) or copying
    from mounted local filesystems.
    """

    def __init__(self, uri: str):
        """Create a new Image object for Testcloud

        :param uri: URI for the image to be represented. this URI must be of a
            supported type (http, https, file)
        :raises TestcloudImageError: if the URI is not of a supported type or cannot be parsed
        """

        # Check/create in exclusive transaction to prevent some races
        with DB.atomic("EXCLUSIVE"):
            uri_data = self._process_uri(uri)
            try:
                self.sqldata = DBImage.select().where(DBImage.name == uri_data["name"]).get()
                self.remote_path = uri
            except peewee.DoesNotExist:
                local_path = os.path.join(config_data.STORE_DIR, uri_data["name"])
                status = "missing"
                if os.path.isfile(local_path):
                    status = "ready"
                self.sqldata = DBImage.create(name=uri_data["name"], status=status, remote_path=uri, local_path=local_path)

    @property
    def name(self):
        return self.sqldata.name

    @name.setter
    def name(self, value):
        if value != self.sqldata.name:
            self.sqldata.name = value
            self.sqldata.save()

    @property
    def status(self):
        return self.sqldata.status

    @status.setter
    def status(self, value):
        if value != self.sqldata.status:
            self.sqldata.status = value
            self.sqldata.save()

    @property
    def last_used(self):
        return self.sqldata.last_used

    @last_used.setter
    def last_used(self, value):
        if value != self.sqldata.last_used:
            self.sqldata.last_used = value
            self.sqldata.save()

    @property
    def remote_path(self):
        return self.sqldata.remote_path

    @remote_path.setter
    def remote_path(self, value):
        if value != self.sqldata.remote_path:
            self.sqldata.remote_path = value
            self.sqldata.save()

    # FIXME - keeping uri for compatibility, get rid of it later
    @property
    def uri(self):
        return self.sqldata.remote_path

    @uri.setter
    def uri(self, value):
        if value != self.sqldata.remote_path:
            self.sqldata.remote_path = value
            self.sqldata.save()

    @property
    def local_path(self):
        return self.sqldata.local_path

    @local_path.setter
    def local_path(self, value):
        if value != self.sqldata.local_path:
            self.sqldata.local_path = value
            self.sqldata.save()

    # FIXME - keeping uri_type for compatibility, get rid of it later
    @property
    def uri_type(self):
        try:
            return self.sqldata.remote_path.split("://", 1)[0]
        except (IndexError, AttributeError):
            return "unknown"

    def _process_uri(self, uri):
        """Process the URI given to find the type, path and imagename contained
        in that URI.

        :param uri: string URI to be processed
        :return: dictionary containing 'type', 'name' and 'path'
        :raise TestcloudImageError: if the URI is invalid or uses an unsupported transport
        """

        prsd = urlparse(uri)
        if prsd.scheme not in ("http", "https", "file"):
            raise TestcloudImageError("invalid uri: only http, https and file schemes are supported: {}".format(uri))

        image_name = os.path.split(prsd.path)[-1]
        if not image_name:
            raise TestcloudImageError("invalid uri: could not find image name: {}".format(uri))

        if image_name.lower().endswith(".xz"):
            image_name = image_name[:-3]
        if image_name.lower().endswith(".box"):
            image_name = f"{image_name[:-4]}.qcow2"

        return {"type": prsd.scheme, "name": image_name, "path": prsd.netloc + prsd.path}

    @classmethod
    def _download_remote_image(cls, remote_url, local_path, progress_callback=None):
        """Download a remote image to the local system, outputting download
        progress as it's downloaded.

        :param remote_url: URL of the image
        :param local_path: local path (including filename) that the image
            will be downloaded to
        """

        u = requests.get(remote_url, stream=True)
        if u.status_code == 404:
            raise TestcloudImageError("Image not found at the given URL: {}".format(remote_url))

        if progress_callback:
            progress_callback(0, 0)

        try:
            with open(local_path + ".part", "wb") as f:

                try:
                    file_size = int(u.headers["content-length"])
                except KeyError:
                    log.warn("Unknown download size.")
                    file_size = -1

                log.info("Downloading {0} ({1} bytes)".format(local_path, file_size))
                bytes_downloaded = 0
                block_size = 4096
                percent_last = 0

                # FIXME - there _must_ be a better way... Not touching this code though...
                # https://stackoverflow.com/questions/16694907/download-large-file-in-python-with-requests
                while True:
                    try:
                        for data in u.iter_content(block_size):
                            bytes_downloaded += len(data)
                            f.write(data)
                            downloaded_coeff = float(bytes_downloaded) / file_size
                            if progress_callback:
                                progress_callback(bytes_downloaded, downloaded_coeff)

                            if config_data.DOWNLOAD_PROGRESS:
                                # TODO: Improve this progress indicator by making
                                # it more readable and user-friendly.
                                status = r"{0}/{1} [{2:.2%}]".format(bytes_downloaded, file_size, downloaded_coeff)
                                status = status + chr(8) * (len(status) + 1)
                                if config_data.DOWNLOAD_PROGRESS_VERBOSE and file_size != -1:
                                    sys.stdout.write(status)
                                else:
                                    if file_size != -1:
                                        percent = int(bytes_downloaded / file_size * 100)
                                    else:
                                        percent = bytes_downloaded
                                    if percent_last != percent:
                                        sys.stdout.write("Downloaded %s %s ...\r" % (percent, "%" if file_size != -1 else "bytes"))
                                        sys.stdout.flush()
                                        percent_last = percent

                    except TypeError:
                        if downloaded_coeff != float(1.0) and file_size != -1:
                            raise TestcloudImageError("Network error during image download, aborting.")
                        #  Rename the file since download has completed
                        os.rename(local_path + ".part", local_path)
                        log.info("Succeeded at downloading {0}".format(local_path))
                        break
                    except Exception:
                        raise TestcloudImageError("Network error during image download, aborting.")

        except OSError:
            # note: suppress inside exception warnings
            raise TestcloudPermissionsError("Problem writing to {}. Are you in group testcloud?".format(local_path)) from None

    @classmethod
    def _adjust_image_selinux(cls, image_path):
        """If SElinux is enabled on the system, change the context of that image
        file such that libguestfs and qemu can use it.

        :param image_path: path to the image to change the context of
        """

        try:
            selinux_active = subprocess.call(["selinuxenabled"])
        except FileNotFoundError:
            logging.debug("selinuxenabled is not present (libselinux-utils package missing?)")
            logging.debug("Assuming selinux is not installed and therefore disabled")
            selinux_active = 1

        if selinux_active != 0:
            log.debug("SELinux not enabled, not changing context of" "image {}".format(image_path))
            return

        image_context = subprocess.call(["chcon", "-h", "-u", "system_u", "-t", "virt_content_t", image_path])
        if image_context == 0:
            log.debug("successfully changed SELinux context for " "image {}".format(image_path))
        else:
            log.error("Error while changing SELinux context on " "image {}".format(image_path))

    def _download_callback(self, bts, coef):
        if (utcnow() - self.last_used).total_seconds() > 2:
            self.last_used = utcnow()

    def download(self):
        if os.path.exists(self.local_path):
            log.debug(f"Image is already present at: {self.local_path}")
            return self.local_path

        raw_local_path = self.local_path
        rpls = self.remote_path.lower().strip()

        if rpls.endswith(".xz"):
            raw_local_path += ".xz"
        if rpls.endswith(".box"):
            raw_local_path = raw_local_path.replace(".qcow2", ".box")

        if rpls.startswith("file://"):
            source_path = self.remote_path[len("file://") :]

            if not os.path.exists(source_path):
                raise FileNotFoundError("Specified image path {} does not exist.".format(source_path))

            try:
                subprocess.check_call(["cp", "-f", source_path, raw_local_path])
            except OSError:
                # note: suppress inside exception warnings
                raise TestcloudPermissionsError("Problem writing to {}. Are you in group testcloud?".format(self.local_path)) from None

        elif rpls.startswith("http://") or rpls.startswith("https://"):
            retries = 0
            while True:
                try:
                    Image._download_remote_image(self.remote_path, raw_local_path, self._download_callback)
                    break
                except TestcloudImageError:
                    retries += 1
                    if retries > config_data.DOWNLOAD_RETRIES:
                        raise TestcloudImageError("Image download failed after %d attempts." % retries)
        else:
            raise TestcloudImageError("Testcloud only supports file, http and https URLs")

        return raw_local_path

    def prepare(self, copy=True):
        """Prepare the image for local use by either downloading the image from
        a remote location or copying/linking it into the image store from a locally
        mounted filesystem

        :param copy: if true image will be copied to backingstores else symlink is created
                     in backingstores instead of copying. Only for file:// type of urls.
        """

        if copy != True:
            log.warning("The `copy` parameter is deprecated, has no effect, and will be removed in future release")

        if os.path.exists(self.local_path):
            self.status = "ready"
            log.debug(f"Image is already present at: {self.local_path}")
            return self.local_path

        if self.status in ["preparing"]:
            i = 0

            log.info("Image is already being prepared by another process. Waiting for it to be ready.")
            while True:
                slp = random.uniform(0.5, 1.5)
                i += slp
                time.sleep(slp)

                if config_data.DOWNLOAD_PROGRESS_VERBOSE:
                    print(".", end="", flush=True)

                with DB.atomic("EXCLUSIVE"):
                    self.sqldata = DBImage.select().where(DBImage.id == self.sqldata.id).get()

                    if self.status == "ready":
                        return self.local_path

                    if self.status in ["missing", "unknown", "failed"]:
                        self.status = "preparing"
                        break

                    if self.status == "preparing" and (utcnow() - self.last_used).total_seconds() > 30:
                        log.info("Download appears to be stalled, taking over")
                        self.status = "preparing"
                        self.last_used = utcnow()
                        break

                if i >= config_data.IMAGE_DOWNLOAD_TIMEOUT:
                    raise TestcloudImageError("Propare process for {} appears stuck".format(self.remote_path))

            if config_data.DOWNLOAD_PROGRESS_VERBOSE:
                print("\n", flush=True)

            log.info("Done waiting")

        self.status = "preparing"

        log.debug("Local downloads will be stored in {}.".format(config_data.STORE_DIR))

        try:
            raw_local_path = self.download()

            if raw_local_path.endswith(".xz"):
                subprocess.call("unxz %s" % raw_local_path, shell=True)

            if raw_local_path.endswith(".box"):
                # For Vagrant boxes we need to:
                # - unpack the .box file (a .tar.gz really)
                # - remove the .box file
                # - rename box.img to `self.local_path` (XXXX.qcow2)
                local_dir, __ = os.path.split(raw_local_path)
                try:
                    # FIXME - This will probably fail (check) when two different .box images are
                    #  extracted at the same time, as it seems the `unpack_archive` creates a `box.img`
                    #  file from any .box file
                    # Probably would be for the best to create a tempdir, extract into it, and then move
                    #  the file to the "final" location?
                    shutil.unpack_archive(raw_local_path, extract_dir=local_dir, format="gztar")
                except ValueError:
                    raise TestcloudImageError("Failed to unpack {}".format(raw_local_path))
                os.remove(raw_local_path)
                os.remove(os.path.join(local_dir, "Vagrantfile"))
                os.remove(os.path.join(local_dir, "metadata.json"))
                os.rename(os.path.join(local_dir, "box.img"), self.local_path)

            Image._adjust_image_selinux(self.local_path)
        except:
            self.status = "failed"
            raise

        self.status = "ready"
        return self.local_path

    def remove(self):
        """Remove the image from disk. This operation cannot be undone."""

        log.debug("removing image {}".format(self.local_path))
        os.remove(self.local_path)
        self.sqldata.delete_instance()

    def destroy(self):
        """A deprecated method. Please call :meth:`remove` instead."""

        log.debug("DEPRECATED: destroy() method was deprecated. Please use remove()")
        self.remove()
