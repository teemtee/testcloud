# -*- coding: utf-8 -*-
# Copyright 2023, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import logging

from testcloud import config
from testcloud import exceptions
from testcloud.distro_utils.misc import parse_latest_qcow

log = logging.getLogger('testcloud.util')
config_data = config.get_config()

def get_rocky_image_url(version:str, arch:str) -> str:
    if version == "latest":
        version = config_data.ROCKY_VERSIONS["latest"]

    STREAM_URL_PREFIX = config_data.ROCKY_URL_PREFIX.format(version, arch)
    IMG_NAME = r'Rocky-{0}-GenericCloud-Base-{0}.[0-9.]-[0-9.]+.{1}.qcow2'.format(version, arch)
    try:
        return parse_latest_qcow(IMG_NAME, STREAM_URL_PREFIX)
    except:
        log.warning("Attempt to find the latest Rocky Linux build failed, using the hardcoded value.")

    if version in config_data.ROCKY_VERSIONS:
        return config_data.ROCKY_VERSIONS[version].format(arch)
    else:
        raise exceptions.TestcloudImageError