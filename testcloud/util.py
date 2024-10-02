# -*- coding: utf-8 -*-
# Copyright 2023, Red Hat, Inc.
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
import socket

from testcloud import config
from testcloud import exceptions
from testcloud.distro_utils.fedora import get_fedora_image_url, get_coreos_image_url, get_fedora_openstack_image_url
from testcloud.distro_utils.centos import get_centos_image_url, get_centos_stream_image_url
from testcloud.distro_utils.alma import get_alma_image_url
from testcloud.distro_utils.rocky import get_rocky_image_url
from testcloud.distro_utils.oracle import get_oracle_image_url
from testcloud.distro_utils.ubuntu import get_ubuntu_image_url
from testcloud.distro_utils.debian import get_debian_image_url

log = logging.getLogger("testcloud.util")
config_data = config.get_config()


def needs_legacy_net(image_name) -> bool:
    """
    Performs a simple regexp that tries to detect presence of el6/7 image name pattern
    Return True in such cases, False otherwise
    """
    return True if re.search(r"(rhel|centos)\D+(6|7).*", image_name.lower()) else False


def create_port_file(instance_name, port):
    """Write the port address found before instance creation to a file
    for easier management later. This is likely going to break
    and need a better solution."""

    with open("{}/instances/{}/port".format(config_data.DATA_DIR, instance_name), "w") as port_file:
        port_file.write(str(port))


def check_port_available(port):
    """
    Checks is a port is available for use
    Returns True/False
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("127.0.0.1", port))
    if result != 0:
        return True
    return False


def find_next_usable_port():
    """
    Returns next usable port for user session vm, starting with SSH_USER_PORT_BASE
    Tries to recycle freed ports from currently used interval
    """
    used_ports = []
    for dir in os.listdir("{}/instances/".format(config_data.DATA_DIR)):
        try:
            with open("{}/instances/{}/port".format(config_data.DATA_DIR, dir), "r") as port_file:
                used_ports.append(int(port_file.readline()))
        except FileNotFoundError:
            continue

    if len(used_ports) == 0:
        used_ports.append(config_data.SSH_USER_PORT_BASE)
    available_in_interval = [i for i in range(config_data.SSH_USER_PORT_BASE, max(used_ports))]
    if len(available_in_interval) > 0:
        i = 0
        recycleable_ports = [item for item in available_in_interval if item not in used_ports]
        length = len(recycleable_ports)
        if length > 0:
            while i < length:
                if check_port_available(recycleable_ports[i]):
                    return recycleable_ports[i]
                else:
                    i = i + 1

    next_port = max(used_ports) + 1
    while not check_port_available(next_port):
        next_port = next_port + 1

    return next_port


def spawn_instance_port_file(instance_name):
    with Filelock():
        path = "{}/instances/{}".format(config_data.DATA_DIR, instance_name)
        if not os.path.isdir(path):
            os.makedirs(path)
        port = find_next_usable_port()
        create_port_file(instance_name, port)
        return port


def generate_mac_address():
    """Create a workable mac address for our instances."""

    hex_mac = [0x52, 0x54, 0x00]  # These 3 are the prefix libvirt uses
    hex_mac += [random.randint(0x00, 0xFF) for x in range(3)]
    mac = ":".join(hex(x)[2:] for x in hex_mac)

    return mac


def verify_url(url: str) -> str:
    if not url:
        raise exceptions.TestcloudImageError

    try:
        requests.head(url).raise_for_status()
        return url
    except requests.exceptions.HTTPError:
        log.error("The generated url ( %s ) for known image doesn't work." % url)
        raise exceptions.TestcloudImageError


def get_image_url(distro_str: str, arch="x86_64", verify=False, additional_handles={}) -> str:
    distro_str = distro_str.lower()
    COREOS = "|".join(d for d in config_data.STREAM_LIST)

    # Position of handles affects program flow
    SUPPORTED_HANDLES = {
        "fedora": {"re": r"^f(edora)?(-|:)?(\d+|rawhide|qa-matrix|branched)?$", "fn": get_fedora_image_url},
        "fedora-coreos": {"re": r"^f(edora-coreos)?(-|:)?(%s)?$" % COREOS, "fn": get_coreos_image_url},
        "fedora-openstack": {"re": r"^f(edora-openstack)?(-|:)?(%s)?$" % COREOS, "fn": get_fedora_openstack_image_url},
        "centos-stream": {"re": r"^c(entos-stream)?(-|:)?(\d+)?$", "fn": get_centos_stream_image_url},
        "coreos": {"re": r"^co(reos)?(-|:)?(%s)?$" % COREOS, "fn": get_coreos_image_url},
        "centos": {"re": r"^c(entos)?(-|:)?(\d+)?$", "fn": get_centos_image_url},
        "ubuntu": {"re": r"^u(buntu)?(-|:)?(\d+)?$", "fn": get_ubuntu_image_url},
        "debian": {"re": r"^d(ebian)?(-|:)?(\d+)?$", "fn": get_debian_image_url},
        "alma": {"re": r"^a(lma)?(-|:)?(\d+)?$", "fn": get_alma_image_url},
        "rocky": {"re": r"^r(ocky)?(-|:)?(\d+)?$", "fn": get_rocky_image_url},
        "oracle": {"re": r"^o(racle)?(-|:)?(\d+)?$", "fn": get_oracle_image_url},
    }

    MERGED_HANDLES = {**SUPPORTED_HANDLES, **additional_handles}
    HELP_LIST = (", ").join(MERGED_HANDLES.keys())

    if not distro_str:
        log.error("No url handle (distro or distro-version) passed, supported handles are: %s" % HELP_LIST)
        raise exceptions.TestcloudImageError

    # regexp matching
    for _, distro in MERGED_HANDLES.items():
        match = re.match(distro["re"], distro_str)
        if match:
            return (verify_url if verify else lambda x: x)(distro["fn"](version=match.group(3) or "latest", arch=arch))

    log.error("Invalid url handle (distro or distro-version) passed, supported handles are: %s" % HELP_LIST)
    raise exceptions.TestcloudImageError


class Filelock(object):
    def __init__(self, timeout=25, wait_time=0.5):
        # We need to define the lock_path here so it won't get overwritten by importing tc's config in this file
        self.lock_path = os.path.join(config_data.DATA_DIR, "testcloud.lock")
        self.fd = open(self.lock_path, "w+")
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
