# -*- coding: utf-8 -*-
# Copyright 2023, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import logging

from testcloud import config
from testcloud import exceptions

log = logging.getLogger("testcloud.util")
config_data = config.get_config()


def get_oracle_image_url(version: str, arch: str) -> str:
    if arch not in ["x86_64", "aarch64"]:
        log.error("Oracle Enterprise Linux supports only x86_64 and aarch64.")
        raise exceptions.TestcloudImageError

    if arch == "x86_64":
        if version == "latest":
            version = config_data.ORACLE_VERSIONS["latest"]
        return config_data.ORACLE_VERSIONS[version]

    if arch == "aarch64":
        if version == "latest":
            version = config_data.ORACLE_A64_VERSIONS["latest"]
        return config_data.ORACLE_A64_VERSIONS[version]
