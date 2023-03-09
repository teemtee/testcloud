# -*- coding: utf-8 -*-
# Copyright 2023, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import re
import requests

from testcloud import exceptions

def parse_latest_qcow(rule:str, url:str) -> str:
        try:
            resp = requests.get(url)
            resp.raise_for_status()
            latest_img_name = sorted(re.findall(rule, resp.text))[-1] or exceptions.TestcloudImageError
            return url + str(latest_img_name)
        except:
            raise exceptions.TestcloudImageError