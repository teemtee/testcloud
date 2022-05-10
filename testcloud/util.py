# -*- coding: utf-8 -*-
# Copyright 2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""
This module contains helper functions for testcloud.
"""

import logging
import random
import requests
import re
import time
import os
import fcntl
import errno

from . import config

try:
    from simplejson.errors import JSONDecodeError
except ImportError:
    from json import JSONDecodeError

log = logging.getLogger('testcloud.util')
config_data = config.get_config()


def generate_mac_address():
    """Create a workable mac address for our instances."""

    hex_mac = [0x52, 0x54, 0x00]  # These 3 are the prefix libvirt uses
    hex_mac += [random.randint(0x00, 0xff) for x in range(3)]
    mac = ':'.join(hex(x)[2:] for x in hex_mac)

    return mac

def get_centos_image_url(version, stream=False, arch="x86_64"):
    if stream:
        versions = config_data.CENTOS_STREAM_VERSIONS
    else:
        versions = config_data.CENTOS_VERSIONS

    if version in versions:
        return versions[version].format(arch)
    else:
        log.error("Don't know the requested CentOS version, allowed values are: %s" % ", ".join(versions.keys()))
        return None

def get_fedora_image_url(version, arch="x86_64"):
    """
    Accepts string specifying desired fedora version, pssible values are:
        - latest (translates to the latest Fedora GA) or XX (where XX is fedora release number)
        - rawhide/branched (the latest successful nightly compose)
        - qa-matrix (nominated compose for testing, can result it either some rawhide nigthly or branched nightly)
        - one of STREAM_LIST (by default one of CoreOS stream names: 'testing', 'stable', 'next')
    Returns url to Fedora Cloud qcow2
    """
    primary_arches = ["x86_64", "aarch64"]
    # get coreos url
    if version in config_data.STREAM_LIST:
        try:
            result = requests.get("https://builds.coreos.fedoraproject.org/streams/%s.json"%version).json()
        except (ConnectionError, IndexError, requests.exceptions.JSONDecodeError):
              log.error("Failed to fetch the image.")
              return None
        url = result['architectures'][arch]['artifacts']['qemu']['formats']['qcow2.xz']['disk']['location']

        return url

    #get Fedora Cloud url
    try:
        oraculum_releases = requests.get('https://packager-dashboard.fedoraproject.org/api/v1/releases').json()
    except (ConnectionError, IndexError, requests.exceptions.JSONDecodeError):
        log.error("Couldn't fetch Fedora releases from oraculum...")
        return None

    if oraculum_releases["fedora"]["branched"] and version == str(oraculum_releases["fedora"]["branched"]):
        version = "branched"

    if not oraculum_releases["fedora"]["branched"] and version == "branched":
        log.warning("Branched release currently doesn't exist, using rawhide...")
        version = "rawhide"

    if version == "qa-matrix":
        if arch != "x86_64":
            log.error("non-x86_64 architecture is not supported with qa-matrix.")
            return None
        try:
            nominated_response = requests.get("https://fedoraproject.org/wiki/Test_Results:Current_Installation_Test")
            return re.findall(r'href=\"(.*.%s.qcow2)\"' % arch, nominated_response.text)[0]
        except (ConnectionError, IndexError):
            log.error("Couldn't fetch the current image from qa-matrix ..")
            return None

    if version == "rawhide" or version == "branched":
        stamp = 0
        try:
            releases = requests.get('https://openqa.fedoraproject.org/nightlies.json').json()
        except (ConnectionError, IndexError, requests.exceptions.JSONDecodeError):
            log.error("Failed to fetch the image.")
            return None
        for release in releases:
            if release["arch"] == arch and release["subvariant"] == "Cloud_Base" and release["type"] == "qcow2":
                if release["mtime"] > stamp and version in release["url"]:
                    url = release["url"]
                    stamp = release["mtime"]
        return url

    if version == "latest":
        version = str(oraculum_releases["fedora"]["stable"])

    try:
        releases = requests.get('https://getfedora.org/releases.json').json()
    except (JSONDecodeError, ConnectionError, requests.exceptions.JSONDecodeError):
        log.error("Couldn't fetch releases list...")
        return None

    url = None
    for release in releases:
        if release["version"] == version and release["variant"] == "Cloud" and release["link"].endswith(".qcow2"):
            # There are links only to primary architecutres in releases.json... much fun
            if arch in primary_arches and release["arch"] == arch:
                url = release["link"]
                break
            elif arch not in primary_arches:
                if release["arch"] == "x86_64":
                    # Try to do a bit of dark magic (that would totally break in no time) to get meaningful url to secondary arch
                    url = release["link"].replace("pub/fedora/linux/releases", "pub/fedora-secondary/releases").replace("x86_64", arch)

    if not url:
        log.error("Expected format is 'fedora:XX' where XX is version number or 'latest', 'rawhide', 'branched' or 'qa-matrix'.")
    return url

def get_ubuntu_releases():
    try:
        releases_resp = requests.get(config_data.UBUNTU_RELEASES_API).json()
    except (ConnectionError, IndexError, requests.exceptions.JSONDecodeError):
        log.error("Failed to fetch Ubuntu releases list.")
        return {}

    return {
        "latest":  [entry["name"] for entry in releases_resp["entries"] if entry["active"] and "Dev" not in entry["status"]][0],
        "entries": [entry["name"] for entry in releases_resp["entries"] if entry["active"] and float(entry["version"]) >= 20]
    }


def get_ubuntu_image_url(version, arch="x86_64"):
    arch_map = {"x86_64": "amd64", "aarch64": "arm64", "ppc64le": "ppc64el", "s390x": "s390x"}

    if arch not in arch_map:
        log.error("Requested architecture is not supported by testcloud for Ubuntu.")
        return None

    if arch != "x86_64":
        config_data.UBUNTU_IMG_URL = config_data.UBUNTU_IMG_URL.replace("-disk-kvm.img", ".img")
    releases = get_ubuntu_releases()
    if len(releases) == 0:
        return None

    if version == "latest":
        return config_data.UBUNTU_IMG_URL % (releases["latest"], releases["latest"], arch_map[arch])
    elif version in releases["entries"]:
        return config_data.UBUNTU_IMG_URL % (version, version, arch_map[arch])
    else:
        log.error("Unknown Ubuntu release, valid releases are: latest, %s" % ', '.join(releases["entries"]))
        return None

def get_debian_image_url(version, arch="x86_64"):
    arch_map = {"x86_64": "amd64", "aarch64": "arm64", "ppc64le": "ppc64el"}

    if arch not in arch_map:
        log.error("Requested architecture is not supported by testcloud for Debian.")
        return None

    if arch != "x86_64":
        config_data.DEBIAN_IMG_URL = config_data.DEBIAN_IMG_URL.replace("genericcloud", "generic")

    inverted_releases = {v: k for k, v in config_data.DEBIAN_RELEASE_MAP.items()}

    if version == "latest":
        return config_data.DEBIAN_IMG_URL % (config_data.DEBIAN_RELEASE_MAP[config_data.DEBIAN_LATEST], config_data.DEBIAN_LATEST, arch_map[arch])
    elif version == "sid":
        return config_data.DEBIAN_IMG_URL % (version, version, arch_map[arch])
    elif version in config_data.DEBIAN_RELEASE_MAP:
        return config_data.DEBIAN_IMG_URL % (config_data.DEBIAN_RELEASE_MAP[version], version, arch_map[arch])
    elif version in config_data.DEBIAN_RELEASE_MAP.values():
        return config_data.DEBIAN_IMG_URL % (version, inverted_releases[version], arch_map[arch])
    else:
        log.error("Unknown Debian release, valid releases are: "
        "latest, %s, %s" % (', '.join(config_data.DEBIAN_RELEASE_MAP), ', '.join(inverted_releases)))
        return None


class Filelock(object):
    def __init__(self, timeout=25, wait_time=0.5):
        # We need to define the lock_path here so it won't get overwritten by importing tc's config in this file
        self.lock_path = os.path.join(config_data.DATA_DIR, 'testcloud.lock')
        self.fd = open(self.lock_path, 'w+')
        self.timeout = timeout
        self.wait_time = wait_time

    def __enter__(self):
        start_time = time.time()
        while 1:
            try:
                fcntl.lockf(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                log.debug("Lock acquired")
                break
            except (OSError, IOError) as ex:
                if ex.errno == errno.EAGAIN:
                    log.debug("Waiting for lock")
                    time.sleep(self.wait_time)
                else:
                    raise ex

            if (start_time + self.timeout) <= time.time():
                log.debug("Lock timeout reached")
                break


    def __exit__(self, exc_type, exc_val, exc_tb):
        fcntl.lockf(self.fd, fcntl.LOCK_UN)
        log.debug("Lock lifted")

    def __del__(self):
        self.fd.close()
