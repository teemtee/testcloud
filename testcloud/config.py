# -*- coding: utf-8 -*-
# Copyright 2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import os
import types

import testcloud


DEFAULT_CONF_DIR = os.path.abspath(os.path.dirname(testcloud.__file__)) + '/../conf'

CONF_DIRS = [DEFAULT_CONF_DIR,
             '{}/.config/testcloud'.format(os.environ['HOME']),
             '/etc/testcloud'
             ]

CONF_FILE = 'settings.py'

_config = None


def get_config():
    '''Retrieve a config instance. If a config instance has already been parsed,
    reuse that parsed instance.

    :return: :class:`.ConfigData` containing configuration values
    '''

    global _config
    if not _config:
        _config = _parse_config()
    return _config


def _parse_config():
    '''Parse config file in a supported location and merge with default values.

    :return: loaded config data merged with defaults from :class:`.ConfigData`
    '''

    config = ConfigData()
    config_filename = _find_config_file()

    if config_filename is not None:
        loaded_config = _load_config(config_filename)
        config.merge_object(loaded_config)

    return config


def _find_config_file():
    '''Look in supported config dirs for a configuration file.

    :return: filename of first discovered file, None if no files are found
    '''

    for conf_dir in CONF_DIRS:
        conf_file = '{}/{}'.format(conf_dir, CONF_FILE)
        if os.path.exists(conf_file):
            return conf_file
    return None


def _load_config(conf_filename):
    '''Load configuration data from a python file. Only loads attrs which are
    named using all caps.

    :param conf_filename: full path to config file to load
    :type conf_filename: str
    :return: object containing configuration values
    '''

    new_conf = types.ModuleType('config')
    new_conf.__file__ = conf_filename
    try:
        with open(conf_filename, 'r') as conf_file:
            exec(compile(conf_file.read(), conf_filename, 'exec'),
                 new_conf.__dict__)
    except IOError as e:
        e.strerror = 'Unable to load config file {}'.format(e.strerror)
        raise
    return new_conf


class ConfigData(object):
    '''Holds configuration data for TestCloud. Is initialized with default
    values which can be overridden.
    '''

    DOWNLOAD_PROGRESS = True
    DOWNLOAD_PROGRESS_VERBOSE = True
    LOG_FILE = None

    # Directories testcloud cares about

    DATA_DIR = "/var/lib/testcloud"
    STORE_DIR = "/var/lib/testcloud/backingstores"

    # libvirt domain XML Template
    # This lives either in the DEFAULT_CONF_DIR or DATA_DIR
    XML_TEMPLATE = "domain-template.jinja"

    # Data for cloud-init

    PASSWORD = 'passw0rd'
    HOSTNAME = 'testcloud'

    META_DATA = """instance-id: iid-123456
local-hostname: %s
    """
    USER_DATA = """#cloud-config
ssh_pwauth: true
password: %s
chpasswd:
  expire: false
users:
  - default
  - name: cloud-user
    plain_text_passwd: %s
    sudo: ALL=(ALL) NOPASSWD:ALL
    lock_passwd: false
runcmd:
  - sed -i -e '/^.*PermitRootLogin/s/^.*$/PermitRootLogin yes/'
    -e '/^.*UseDNS/s/^.*$/UseDNS no/'
    -e '/^.*GSSAPIAuthentication/s/^.*$/GSSAPIAuthentication no/'
    /etc/ssh/sshd_config
  - systemctl reload sshd
  - [sh, -c, 'if [ ! -f /etc/systemd/network/20-tc-usernet.network ] &&
  systemctl status systemd-networkd | grep -q "enabled;\\svendor\\spreset:\\senabled";
  then mkdir -p /etc/systemd/network/ &&
  echo "[Match]" >> /etc/systemd/network/20-tc-usernet.network &&
  echo "Name=en*" >> /etc/systemd/network/20-tc-usernet.network &&
  echo "[Network]" >> /etc/systemd/network/20-tc-usernet.network &&
  echo "DHCP=yes" >> /etc/systemd/network/20-tc-usernet.network; fi']
  - [sh, -c, 'if systemctl status systemd-networkd | grep -q "enabled;\\svendor\\spreset:\\senabled"; then
  systemctl restart systemd-networkd; fi']
  - [sh, -c, 'if cat /etc/os-release | grep -q platform:el8; then systemctl restart sshd; fi']
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
    CMD_LINE_ARGS_COREOS = ['-fw_cfg' ,]
    CMD_LINE_ENVS_COREOS = {}
    # timeout, in seconds for instance boot process
    BOOT_TIMEOUT = 70

    # Maximum space (in GiB) that unused images can occupy in /var/lib/testcloud/backingstores directory
    # Once the limit is reached, testcloud will attempt to remove oldest files
    # before creating a new instance
    # 0 = unlimited
    BACKINGSTORE_SIZE = 0

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

    #stream of Coreos repo
    STREAM = 'testing'

    #stream list of Coreos repo
    STREAM_LIST = ['testing', 'stable', 'next']

    #version of fedora repo
    VERSION = 'latest'

    #number of vcpu
    VCPUS = 2
    # Port base for userspace sessions for SSH forward
    SSH_USER_PORT_BASE = 10022

    # Data for CentOS Vagrant
    COS_VAG_USER = "root"
    COS_VAG_PASS = "vagrant"
    VAGRANT_USER_SESSION_WAIT = 45 # How long testcloud will wait before typing into the vms's console

    # There currently isn't an api way to fetch the current CentOS Releases
    CENTOS_VERSIONS = {
        "7":      "https://cloud.centos.org/centos/7/images/CentOS-7-{0}-GenericCloud-2111.qcow2",
        "8":      "https://cloud.centos.org/centos/8/{0}/images/CentOS-8-GenericCloud-8.4.2105-20210603.0.{0}.qcow2",
        "latest": "https://cloud.centos.org/centos/8/{0}/images/CentOS-8-GenericCloud-8.4.2105-20210603.0.{0}.qcow2"
    }

    CENTOS_STREAM_VERSIONS = {
        "8":      "https://cloud.centos.org/centos/8-stream/{0}/images/CentOS-Stream-GenericCloud-8-20220913.0.{0}.qcow2",
        "9":      "https://cloud.centos.org/centos/9-stream/{0}/images/CentOS-Stream-GenericCloud-9-20221101.0.{0}.qcow2",
        "latest": "https://cloud.centos.org/centos/9-stream/{0}/images/CentOS-Stream-GenericCloud-9-20221101.0.{0}.qcow2"
    }

    DEBIAN_RELEASE_MAP = {"10": "buster","11": "bullseye"}
    DEBIAN_LATEST = "11"
    DEBIAN_IMG_URL = "https://cloud.debian.org/images/cloud/%s/daily/latest/debian-%s-genericcloud-%s-daily.qcow2"
    UBUNTU_RELEASES_API = "https://api.launchpad.net/devel/ubuntu/series"
    UBUNTU_IMG_URL = "https://cloud-images.ubuntu.com/%s/current/%s-server-cloudimg-%s-disk-kvm.img"

    def merge_object(self, obj):
        '''Overwrites default values with values from a python object which have
        names containing all upper case letters.

        :param obj: python object containing configuration values
        :type obj: python object
        '''

        for key in dir(obj):
            if key.isupper():
                setattr(self, key, getattr(obj, key))
