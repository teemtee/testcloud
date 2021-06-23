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
        return versions[version] % (arch, arch)
    else:
        log.error("Don't know the requested CentOS version, allowed values are: %s" % str(versions.keys()))
        return None

def get_fedora_image_url(version, arch="x86_64"):
    """
    Accepts string specifying desired fedora version, pssible values are:
        - latest (translates to the latest Fedora GA) or XX (where XX is fedora release number)
        - rawhide (the latest successful nightly compose)
        - qa-matrix (nominated compose for testing, can result it either some rawhide nigthly or branched nightly)
        - one of STREAM_LIST (by default one of CoreOS stream names: 'testing', 'stable', 'next')
    Returns url to Fedora Cloud qcow2
    """
    # get coreos url
    if version in config_data.STREAM_LIST:
        try:
            result = requests.get("https://builds.coreos.fedoraproject.org/streams/%s.json"%version).json()
        except (ConnectionError, IndexError):
              log.error("Failed to fetch the image.")
              return None
        url = result['architectures'][arch]['artifacts']['qemu']['formats']['qcow2.xz']['disk']['location']

        return url
    #get testcloud url
    if version == "qa-matrix":
        try:
            nominated_response = requests.get("https://fedoraproject.org/wiki/Test_Results:Current_Installation_Test")
            return re.findall(r'href=\"(.*.%s.qcow2)\"' % arch, nominated_response.text)[0]
        except (ConnectionError, IndexError):
            log.error("Couldn't fetch the current image from qa-matrix ..")
            return None

    if version == "rawhide":
        stamp = 0
        try:
            releases = requests.get('https://openqa.fedoraproject.org/nightlies.json').json()
        except (ConnectionError, IndexError):
            log.error("Failed to fetch the image.")
            return None
        for release in releases:
            if release["arch"] == arch and release["subvariant"] == "Cloud_Base" and release["type"] == "qcow2":
                if release["mtime"] > stamp:
                    url = release["url"]
                    stamp = release["mtime"]
        return url

    if version == "latest":
        try:
            latest_release = requests.get('https://packager-dashboard.fedoraproject.org/api/v1/releases').json()
        except (JSONDecodeError, ConnectionError):
            log.error("Couldn't fetch the latest Fedora release...")
            log.error("Expected format is 'fedora:XX' where XX is version number or 'latest', 'rawhide' or 'qa-matrix'.")
            return None
        version = str(latest_release["fedora"]["stable"])

    try:
        releases = requests.get('https://getfedora.org/releases.json').json()
    except (JSONDecodeError, ConnectionError):
        log.error("Couldn't fetch releases list...")
        return None

    url = None
    for release in releases:
        if release["version"] == version and release["variant"] == "Cloud" and release["link"].endswith(".qcow2"):
            # Currently, we support just the x86_64
            if release["arch"] == arch:
                url = release["link"]
                break

    return url
