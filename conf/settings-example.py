# Commented out default values with details are displayed below. If you want
# to change the values, make sure this file is available in one of the three
# supported config locations:
# - conf/settings.py in the git checkout
# - ~/.config/testcloud/settings.py
# - /etc/testcloud/settings.py


#DOWNLOAD_PROGRESS = True
#DOWNLOAD_PROGRESS_VERBOSE = True
#LOG_FILE = None


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
#password: %s
#chpasswd: { expire: False }
#ssh_pwauth: True
#"""

#COREOS_DATA = """variant: fcos
#version: 1.4.0
#passwd:
#  users:
#    - name: cloud-user
#      ssh_authorized_keys:
#        - %s
#    """

## Extra cmdline args for the qemu invocation ##
## Customize as needed :)

#CMD_LINE_ARGS = []
#CMD_LINE_ENVS = {}

# Extra coreos cmdline args for the qemu invocation.
# Customize as needed :)
#CMD_LINE_ARGS_COREOS = ['-fw_cfg' ,]
#CMD_LINE_ENVS_COREOS = {}

# The timeout, in seconds, to wait for an instance to boot before
# failing the boot process. Setting this to 0 disables waiting and
# returns immediately after starting the boot process.
#BOOT_TIMEOUT = 70

# Maximum space (in GiB) that unused images can occupy in /var/lib/testcloud/backingstores directory
# Once the limit is reached, testcloud will attempt to remove oldest files
# before creating a new instance
# 0 = unlimited
BACKINGSTORE_SIZE = 4

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

# Data for CentOS Vagrant
#COS_VAG_USER = "root"
#COS_VAG_PASS = "vagrant"
#VAGRANT_USER_SESSION_WAIT = 45 # How long testcloud will wait before typing into the vms's console
