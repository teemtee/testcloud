# -*- coding: utf-8 -*-
# Copyright 2023, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import logging
import re
import requests

from testcloud import exceptions, config
from packaging.version import Version

config_data = config.get_config()
log = logging.getLogger("testcloud.util")


def parse_latest_qcow(rule: str, url: str) -> str:
    session = get_requests_session()

    try:
        resp = session.get(url)
        resp.raise_for_status()
        latest_img_name = sorted(re.findall(rule, resp.text))[-1] or exceptions.TestcloudImageError
        return url + str(latest_img_name)
    except:
        raise exceptions.TestcloudImageError


def get_requests_session():
    try:
        assert config_data.CACHE_IMAGES
        import requests_cache

        assert Version(requests_cache.__version__) >= Version("1.2")

        log.debug("Using local image url cache...")
        return requests_cache.CachedSession(
            cache_name="{}/testcloud_image_resolve_cache".format(config_data.DATA_DIR),
            backend="sqlite",
            stale_if_error=True,
            expire_after=config_data.TRUST_DEADLINE * 60 * 60 * 24,
        )
    except (ImportError, AssertionError):
        log.debug("Not using local image url cache due to config or unmet dependencies...")
        return requests.Session()
