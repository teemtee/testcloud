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

def get_centos_image_url(version:str, arch:str) -> str:
    return _get_centos_image_url(version=version, stream=False, arch=arch)

def get_centos_stream_image_url(version:str, arch:str) -> str:
    return _get_centos_image_url(version=version, stream=True, arch=arch)

def _get_centos_image_url(version:str, stream:bool, arch:str) -> str:
    if stream:
        # CentOS Stream
        if version == "latest":
            version = config_data.CENTOS_STREAM_VERSIONS["latest"]

        # Try to dynamically get the latest at first
        STREAM_URL_PREFIX = config_data.CENTOS_STREAM_URL_PREFIX.format(version, arch)
        IMG_NAME = r'CentOS-Stream-GenericCloud-{0}-[0-9.]+.{1}.qcow2'.format(version, arch)
        try:
            return parse_latest_qcow(IMG_NAME, STREAM_URL_PREFIX)
        except:
            log.warning("Attempt to find the latest CentOS Stream build failed, using the hardcoded value.")
        versions = config_data.CENTOS_STREAM_VERSIONS
    else:
        # Legacy CentOS
        if version == "latest":
            version = config_data.CENTOS_VERSIONS["latest"]
        versions = config_data.CENTOS_VERSIONS

    if version in versions:
        return versions[version].format(arch)
    else:
        log.error("Don't know the requested CentOS version, allowed values are: %s" % ", ".join(versions.keys()))
        raise exceptions.TestcloudImageError