# Commented out default values with details are displayed below. If you want
# to change the values, make sure this file is available in one of the three
# supported config locations:
# - conf/settings.py in the git checkout
# - ~/.config/testcloud/settings.py
# - /etc/testcloud/settings.py


#DEBUG = False
#LOG_FILE = None

# Downloader config
#DOWNLOAD_PROGRESS = True
#DOWNLOAD_PROGRESS_VERBOSE = True
#DOWNLOAD_RETRIES = 2

## Directories for data and cached downloaded images ##

#DATA_DIR = "/var/lib/testcloud/"
#STORE_DIR = "/var/lib/testcloud/backingstores"


## Data for cloud-init ##

#PASSWORD = 'passw0rd'
#HOSTNAME = 'testcloud'

#META_DATA = """instance-id: iid-123456
#local-hostname: %s
#"""
## Read http://cloudinit.readthedocs.io/en/latest/topics/examples.html to see
## what options you can use here.
#USER_DATA = """#cloud-config
#ssh_pwauth: true
#password: ${password}
#chpasswd:
#  expire: false
#users:
#  - default
#  - name: cloud-user
#    plain_text_passwd: ${password}
#    sudo: ALL=(ALL) NOPASSWD:ALL
#    lock_passwd: false
#runcmd:
#${runcommands}
#"""

#COREOS_DATA = """variant: fcos
#version: 1.4.0
#passwd:
#  users:
#    - name: cloud-user
#      ssh_authorized_keys:
#        - %s
#"""

## Extra cmdline args for the qemu invocation ##
## Customize as needed :)

#CMD_LINE_ARGS = []
#CMD_LINE_ENVS = {}

# Extra coreos cmdline args for the qemu invocation.
# Customize as needed :)
#CMD_LINE_ARGS_COREOS = []
#CMD_LINE_ENVS_COREOS = {}

# The timeout, in seconds, to wait for an instance to boot before
# failing the boot process. Setting this to 0 disables waiting and
# returns immediately after starting the boot process.
#BOOT_TIMEOUT = 160
# timeout after which we should kill unfinished downloads of images
#IMAGE_DOWNLOAD_TIMEOUT = 1800

# Maximum space (in GiB) that unused images can occupy in /var/lib/testcloud/backingstores directory
# Once the limit is reached, testcloud will attempt to remove oldest files
# before creating a new instance
# 0 = unlimited
BACKINGSTORE_SIZE = 4

# Is reusing the local image url cache an option?
#CACHE_IMAGES = True

# # How old can a local image url cache be to take it as viable
#TRUST_DEADLINE = 7 # Days

# ram size, in MiB
#RAM = 768
#RAM_COREOS = 2048

# Desired size, in GiB of instance disks. 0 leaves disk capacity
# identical to source image
#DISK_SIZE = 0
#DISK_SIZE_COREOS = 10

# Number of retries when stopping of instance fails (host is busy)
#STOP_RETRIES = 3

# Waiting time between stop retries, in seconds
#STOP_RETRY_WAIT = 1

# Desired VM type: False = BIOS, True = UEFI
#UEFI = False
#stream of Coreos repo
#STREAM = 'testing'

#stream list of Coreos repo
#STREAM_LIST = ['testing', 'stable', 'next']

#version of fedora repo
#VERSION = 'latest'

#number of vcpu
#VCPUS = 2

# Port base for userspace sessions for SSH forward
#SSH_USER_PORT_BASE = 10022

# Data for Vagrant
#VAGRANT_USER = "root"
#VAGRANT_PASS = "vagrant"
#VAGRANT_USER_SESSION_WAIT = 45 # How long testcloud will wait before typing into the vms's console

# Known vagrant distros
#VARGANT_CENTOS_SH = "dnf -y install cloud-init && cloud-init init && reboot\n"
#VAGRANT_FEDORA_SH = "systemctl unmask cloud-init && systemctl start cloud-init && systemctl start sshd\n"
