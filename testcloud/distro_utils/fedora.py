# -*- coding: utf-8 -*-
# Copyright 2023, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import logging
import re
import requests

from testcloud import config
from testcloud import exceptions

log = logging.getLogger('testcloud.util')
config_data = config.get_config()

def get_coreos_image_url(version:str, arch:str) -> str:
    if version == "latest":
        version = "stable"

    if version not in config_data.STREAM_LIST:
        raise exceptions.TestcloudImageError

    return get_fedora_image_url(version, arch)

def get_fedora_image_url(version:str, arch:str) -> str:
    """
    Accepts string specifying desired fedora version, pssible values are:
        - latest (translates to the latest Fedora GA) or XX (where XX is fedora release number)
        - rawhide/branched (the latest successful nightly compose)
        - qa-matrix (nominated compose for testing, can result it either some rawhide nigthly or branched nightly)
        - one of STREAM_LIST (by default one of CoreOS stream names: 'testing', 'stable', 'next')
    Returns url to Fedora Cloud qcow2
    """
    primary_arches = ["x86_64", "aarch64"]
    url = ""

    # get coreos url
    if version in config_data.STREAM_LIST:
        try:
            result = requests.get("https://builds.coreos.fedoraproject.org/streams/%s.json"%version).json()
        except (ConnectionError, IndexError, requests.exceptions.JSONDecodeError):
              log.error("Failed to fetch the image.")
              raise exceptions.TestcloudImageError
        url = str(result['architectures'][arch]['artifacts']['qemu']['formats']['qcow2.xz']['disk']['location'])
        return url

    #get Fedora Cloud url
    try:
        oraculum_releases = requests.get('https://packager-dashboard.fedoraproject.org/api/v1/releases').json()
    except (ConnectionError, IndexError, requests.exceptions.JSONDecodeError):
        log.error("Couldn't fetch Fedora releases from oraculum...")
        raise exceptions.TestcloudImageError

    if oraculum_releases["fedora"]["branched"] and version == str(oraculum_releases["fedora"]["branched"]):
        version = "branched"

    if not oraculum_releases["fedora"]["branched"] and version == "branched":
        log.warning("Branched release currently doesn't exist, using rawhide...")
        version = "rawhide"

    if version == str(oraculum_releases["fedora"]["rawhide"]):
        version = "rawhide"

    if version == "qa-matrix":
        if arch != "x86_64":
            log.error("non-x86_64 architecture is not supported with Fedora qa-matrix.")
            raise exceptions.TestcloudImageError
        try:
            nominated_response = requests.get("https://fedoraproject.org/wiki/Test_Results:Current_Installation_Test")
            return str(re.findall(r'href=\"(.*.%s.qcow2)\"' % arch, nominated_response.text)[0])
        except (ConnectionError, IndexError):
            log.error("Couldn't fetch the current Fedora image from qa-matrix ..")
            raise exceptions.TestcloudImageError

    if version == "rawhide" or version == "branched":
        stamp = 0
        try:
            releases = requests.get('https://openqa.fedoraproject.org/nightlies.json').json()
        except (ConnectionError, IndexError, requests.exceptions.JSONDecodeError):
            log.error("Failed to fetch the image.")
            raise exceptions.TestcloudImageError
        for release in releases:
            if release["arch"] == arch and release["subvariant"] == "Cloud_Base" and release["type"] == "qcow2":
                if release["mtime"] > stamp and version in release["url"]:
                    url = release["url"]
                    stamp = release["mtime"]
        if not url:
            log.error("Failed to find/guess url for Fedora %s image" % version)
            raise exceptions.TestcloudImageError
        return str(url)

    if version == "latest":
        version = str(oraculum_releases["fedora"]["stable"])

    try:
        releases = requests.get('https://getfedora.org/releases.json').json()
    except (ConnectionError, requests.exceptions.JSONDecodeError):
        log.error("Couldn't fetch Fedora releases list...")
        raise exceptions.TestcloudImageError

    url = ""
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
        raise exceptions.TestcloudImageError
    return str(url)
