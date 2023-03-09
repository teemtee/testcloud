# -*- coding: utf-8 -*-
# Copyright 2023, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import logging
import requests

from testcloud import config
from testcloud import exceptions

log = logging.getLogger('testcloud.util')
config_data = config.get_config()

def get_ubuntu_releases() -> dict:
    try:
        releases_resp = requests.get(config_data.UBUNTU_RELEASES_API).json()
    except (ConnectionError, IndexError, requests.exceptions.JSONDecodeError):
        log.error("Failed to fetch Ubuntu releases list.")
        raise exceptions.TestcloudImageError

    return {
        "latest":  [entry["name"] for entry in releases_resp["entries"] if entry["active"] and "Dev" not in entry["status"]][0],
        "entries": [entry["name"] for entry in releases_resp["entries"] if entry["active"] and float(entry["version"]) >= 20]
    }


def get_ubuntu_image_url(version:str, arch:str) -> str:
    arch_map = {"x86_64": "amd64", "aarch64": "arm64", "ppc64le": "ppc64el", "s390x": "s390x"}

    if arch not in arch_map:
        log.error("Requested architecture is not supported by testcloud for Ubuntu.")
        raise exceptions.TestcloudImageError

    if arch != "x86_64":
        config_data.UBUNTU_IMG_URL = config_data.UBUNTU_IMG_URL.replace("-disk-kvm.img", ".img")
    releases = get_ubuntu_releases()
    if len(releases) == 0:
        raise exceptions.TestcloudImageError

    if version == "latest":
        return config_data.UBUNTU_IMG_URL % (releases["latest"], releases["latest"], arch_map[arch])
    elif version in releases["entries"]:
        return config_data.UBUNTU_IMG_URL % (version, version, arch_map[arch])
    else:
        log.error("Unknown Ubuntu release, valid releases are: latest, %s" % ', '.join(releases["entries"]))
        raise exceptions.TestcloudImageError