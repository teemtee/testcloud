# -*- coding: utf-8 -*-
# Copyright 2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import os
import types

import testcloud

DEFAULT_CONF_DIR = os.path.abspath(os.path.dirname(testcloud.__file__)) + "/../conf"

CONF_DIRS = [
    DEFAULT_CONF_DIR,
    "{}/.config/testcloud".format(os.environ["HOME"]),
    "/etc/testcloud",
]

CONF_FILE = "settings.py"

_config = None


def get_config():
    """Retrieve a config instance. If a config instance has already been parsed,
    reuse that parsed instance.

    :return: :class:`.ConfigData` containing configuration values
    """

    global _config
    if not _config:
        _config = _parse_config()
    return _config


def _parse_config():
    """Parse config file in a supported location and merge with default values.

    :return: loaded config data merged with defaults from :class:`.ConfigData`
    """

    config = ConfigData()
    config_filename = _find_config_file()

    if config_filename is not None:
        loaded_config = _load_config(config_filename)
        config.merge_object(loaded_config)

    return config


def _find_config_file():
    """Look in supported config dirs for a configuration file.

    :return: filename of first discovered file, None if no files are found
    """

    for conf_dir in CONF_DIRS:
        conf_file = "{}/{}".format(conf_dir, CONF_FILE)
        if os.path.exists(conf_file):
            return conf_file
    return None


def _load_config(conf_filename):
    """Load configuration data from a python file. Only loads attrs which are
    named using all caps.

    :param conf_filename: full path to config file to load
    :type conf_filename: str
    :return: object containing configuration values
    """

    new_conf = types.ModuleType("config")
    new_conf.__file__ = conf_filename
    try:
        with open(conf_filename, "r") as conf_file:
            exec(compile(conf_file.read(), conf_filename, "exec"), new_conf.__dict__)
    except IOError as e:
        e.strerror = "Unable to load config file {}".format(e.strerror)
        raise
    return new_conf


class ConfigData(object):
    """Holds configuration data for TestCloud. Is initialized with default
    values which can be overridden.
    """

    DEBUG = False
    LOG_FILE = None

    # Downloader config
    DOWNLOAD_PROGRESS = True
    DOWNLOAD_PROGRESS_VERBOSE = True
    DOWNLOAD_RETRIES = 2

    # Directories testcloud cares about

    DATA_DIR = "/var/lib/testcloud"
    STORE_DIR = "/var/lib/testcloud/backingstores"

    # Data for cloud-init

    PASSWORD = "passw0rd"
    HOSTNAME = "testcloud"

    META_DATA = """instance-id: iid-123456
local-hostname: %s
"""
    USER_DATA = """#cloud-config
ssh_pwauth: true
password: ${password}
chpasswd:
  expire: false
users:
  - default
  - name: cloud-user
    plain_text_passwd: ${password}
    sudo: ALL=(ALL) NOPASSWD:ALL
    lock_passwd: false
runcmd:
${runcommands}
"""
    COREOS_DATA = """variant: fcos
version: 1.4.0
passwd:
  users:
    - name: cloud-user
      groups:
        - wheel
      password_hash: $y$j9T$90Mqu2Viusm6XbBpEBUW60$IF9ZBdoOtbJel4UxNLJDduWBj1ND93FdO5cTDndcXjB
      ssh_authorized_keys:
        - %s
storage:
  files:
    - path: /etc/ssh/sshd_config.d/20-enable-passwords.conf
      mode: 0644
      contents:
        inline: |
          # Fedora CoreOS disables SSH password login by default.
          # Enable it.
          # This file must sort before 40-disable-passwords.conf.
          PasswordAuthentication yes
"""

    # Extra cmdline args for the qemu invocation.
    # Customize as needed :)
    CMD_LINE_ARGS = []
    CMD_LINE_ENVS = {}

    # Extra coreos cmdline args for the qemu invocation.
    # Customize as needed :)
    CMD_LINE_ARGS_COREOS = []
    CMD_LINE_ENVS_COREOS = {}
    # timeout, in seconds for instance boot process
    BOOT_TIMEOUT = 160
    # timeout after which we should kill unfinished downloads of images
    IMAGE_DOWNLOAD_TIMEOUT = 1800

    # Maximum space (in GiB) that unused images can occupy in /var/lib/testcloud/backingstores directory
    # Once the limit is reached, testcloud will attempt to remove oldest files
    # before creating a new instance
    # 0 = unlimited
    BACKINGSTORE_SIZE = 0

    # Is reusing the local image url cache an option?
    CACHE_IMAGES = True

    # How old can a local image url cache be to take it as viable
    TRUST_DEADLINE = 7  # Days

    # ram size, in MiB
    RAM = 768
    RAM_COREOS = 2048

    # Desired size, in GiB of instance disks. 0 leaves disk capacity
    # identical to source image
    DISK_SIZE = 0
    DISK_SIZE_COREOS = 10

    # Number of retries when stopping of instance fails (host is busy)
    STOP_RETRIES = 3

    # Waiting time between stop retries, in seconds
    STOP_RETRY_WAIT = 1

    # Desired VM type: False = BIOS, True = UEFI
    UEFI = False

    # stream of Coreos repo
    STREAM = "testing"

    # stream list of Coreos repo
    STREAM_LIST = ["testing", "stable", "next"]

    # version of fedora repo
    VERSION = "latest"

    # number of vcpu
    VCPUS = 2
    # Port base for userspace sessions for SSH forward
    SSH_USER_PORT_BASE = 10022

    # Data for Vagrant
    VAGRANT_USER = "root"
    VAGRANT_PASS = "vagrant"
    VAGRANT_USER_SESSION_WAIT = 45  # How long testcloud will wait before typing into the vms's console

    # Known vagrant distros
    VARGANT_CENTOS_SH = "dnf -y install cloud-init && cloud-init init && reboot\n"
    VAGRANT_FEDORA_SH = "systemctl unmask cloud-init && systemctl start cloud-init && systemctl start sshd\n"

    # There currently isn't an api way to fetch the current CentOS Releases
    CENTOS_VERSIONS = {
        "7": "https://cloud.centos.org/centos/7/images/CentOS-7-{0}-GenericCloud-2211.qcow2",
        "8": "https://cloud.centos.org/centos/8/{0}/images/CentOS-8-GenericCloud-8.4.2105-20210603.0.{0}.qcow2",
        "latest": "8",
    }

    # Used to try to auto-fetch the latest qcow2
    CENTOS_STREAM_URL_PREFIX = "https://cloud.centos.org/centos/{0}-stream/{1}/images/"
    CENTOS_STREAM_VERSIONS = {
        "8": "https://cloud.centos.org/centos/8-stream/{0}/images/CentOS-Stream-GenericCloud-8-20240603.0.{0}.qcow2",
        "9": "https://cloud.centos.org/centos/9-stream/{0}/images/CentOS-Stream-GenericCloud-9-20240715.0.{0}.qcow2",
        "10": "https://odcs.stream.centos.org/stream-10/production/CentOS-Stream-10-20240709.0/compose/BaseOS/{0}/images/CentOS-Stream-GenericCloud-10-20240709.0.{0}.qcow2",
        "latest": "9",
    }

    ROCKY_URL_PREFIX = "https://download.rockylinux.org/pub/rocky/{0}/images/{1}/"
    ROCKY_VERSIONS = {
        "8": "https://download.rockylinux.org/pub/rocky/8/images/{0}/Rocky-8-GenericCloud-Base-8.10-20240528.0.{0}.qcow2",
        "9": "https://download.rockylinux.org/pub/rocky/9/images/{0}/Rocky-9-GenericCloud-Base-9.4-20240609.1.{0}.qcow2",
        "latest": "9",
    }

    ALMA_URL_PREFIX = "https://repo.almalinux.org/almalinux/{0}/cloud/{1}/images/"
    ALMA_VERSIONS = {
        "8": "https://repo.almalinux.org/almalinux/8/cloud/{0}/images/AlmaLinux-8-GenericCloud-8.10-20240530.{0}.qcow2",
        "9": "https://repo.almalinux.org/almalinux/9/cloud/{0}/images/AlmaLinux-9-GenericCloud-9.4-20240507.{0}.qcow2",
        "latest": "9",
    }

    # https://yum.oracle.com/oracle-linux-templates.html
    ORACLE_VERSIONS = {
        "7": "https://yum.oracle.com/templates/OracleLinux/OL7/u9/x86_64/OL7U9_x86_64-kvm-b218.qcow2",
        "8": "https://yum.oracle.com/templates/OracleLinux/OL8/u10/x86_64/OL8U10_x86_64-kvm-b237.qcow2",
        "9": "https://yum.oracle.com/templates/OracleLinux/OL9/u4/x86_64/OL9U4_x86_64-kvm-b234.qcow2",
        "latest": "9",
    }

    ORACLE_A64_VERSIONS = {
        "8": "https://yum.oracle.com/templates/OracleLinux/OL8/u10/aarch64/OL8U10_aarch64-kvm-cloud-b100.qcow2",
        "9": "https://yum.oracle.com/templates/OracleLinux/OL9/u4/aarch64/OL9U4_aarch64-kvm-cloud-b90.qcow2",
        "latest": "9",
    }

    DEBIAN_RELEASE_MAP = {"10": "buster", "11": "bullseye", "12": "bookworm"}
    DEBIAN_LATEST = "12"
    DEBIAN_IMG_URL = "https://cloud.debian.org/images/cloud/%s/daily/latest/debian-%s-genericcloud-%s-daily.qcow2"

    UBUNTU_RELEASES_API = "https://api.launchpad.net/devel/ubuntu/series"
    UBUNTU_IMG_URL = "https://cloud-images.ubuntu.com/%s/current/%s-server-cloudimg-%s.img"

    def merge_object(self, obj):
        """Overwrites default values with values from a python object which have
        names containing all upper case letters.

        :param obj: python object containing configuration values
        :type obj: python object
        """

        for key in dir(obj):
            if key.isupper():
                setattr(self, key, getattr(obj, key))
