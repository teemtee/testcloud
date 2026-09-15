# -*- coding: utf-8 -*-
# Copyright 2023, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import logging

from testcloud import config
from testcloud import exceptions

log = logging.getLogger("testcloud.util")
config_data = config.get_config()


def get_debian_image_url(version: str, arch: str) -> list[str]:
    arch_map = {"x86_64": "amd64", "aarch64": "arm64", "ppc64le": "ppc64el"}

    if arch not in arch_map:
        log.error("Requested architecture is not supported by testcloud for Debian.")
        raise exceptions.TestcloudImageError

    url_templates = config_data.DEBIAN_IMG_URL
    if isinstance(url_templates, str):
        url_templates = [url_templates]

    if arch != "x86_64":
        url_templates = [t.replace("genericcloud", "generic") for t in url_templates]

    inverted_releases = {v: k for k, v in config_data.DEBIAN_RELEASE_MAP.items()}

    if version == "latest":
        args = (
            config_data.DEBIAN_RELEASE_MAP[config_data.DEBIAN_LATEST],
            config_data.DEBIAN_LATEST,
            arch_map[arch],
        )
    elif version == "sid":
        args = (version, version, arch_map[arch])
    elif version in config_data.DEBIAN_RELEASE_MAP:
        args = (config_data.DEBIAN_RELEASE_MAP[version], version, arch_map[arch])
    elif version in inverted_releases:
        args = (version, inverted_releases[version], arch_map[arch])
    else:
        log.error(
            "Unknown Debian release, valid releases are: "
            "latest, %s, %s" % (", ".join(config_data.DEBIAN_RELEASE_MAP), ", ".join(inverted_releases))
        )
        raise exceptions.TestcloudImageError

    return [t % args for t in url_templates]
