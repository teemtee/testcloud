# -*- coding: utf-8 -*-
# Copyright 2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""
Representation of a Testcloud spawned (or to-be-spawned) virtual machine
"""

import os

import subprocess
import logging
import time

import libvirt
import shutil
import platform
import socket

from testcloud import config
from testcloud import util
from testcloud.exceptions import TestcloudInstanceError, TestcloudPermissionsError
from testcloud.domain_configuration import *

config_data = config.get_config()

log = logging.getLogger('testcloud.instance')

#: mapping domain state constants from libvirt to a known set of strings
DOMAIN_STATUS_ENUM = {libvirt.VIR_DOMAIN_NOSTATE: 'no state',
                      libvirt.VIR_DOMAIN_RUNNING: 'running',
                      libvirt.VIR_DOMAIN_BLOCKED: 'blocked',
                      libvirt.VIR_DOMAIN_PAUSED:  'paused',
                      libvirt.VIR_DOMAIN_SHUTDOWN: 'shutdown',
                      libvirt.VIR_DOMAIN_SHUTOFF: 'shutoff',
                      libvirt.VIR_DOMAIN_CRASHED: 'crashed',
                      libvirt.VIR_DOMAIN_PMSUSPENDED: 'suspended'
                      }


def _list_instances():
    """List existing instances currently known to testcloud

    :returns: dict of instance names and their ip address
    """

    instance_list = []

    instance_dir = os.listdir('{}/instances'.format(config_data.DATA_DIR))
    for dir in instance_dir:
        instance_details = {}
        instance_details['name'] = dir
        try:
            with open("{}/instances/{}/ip".format(config_data.DATA_DIR, dir), 'r') as inst:
                instance_details['ip'] = inst.readline().strip()

        except IOError:
            instance_details['ip'] = None

        try:
            with open("{}/instances/{}/port".format(config_data.DATA_DIR, dir), 'r') as inst:
                instance_details['port'] = inst.readline().strip()

        except IOError:
            instance_details['port'] = 22

        instance_list.append(instance_details)

    return instance_list


def _list_domains(connection):
    """List known domains for a given hypervisor connection.

    :param connection: libvirt compatible hypervisor connection
    :returns: dictionary mapping of name -> state
    :rtype: dict
    """

    domains = {}
    conn = libvirt.openReadOnly(connection)
    for domain in conn.listAllDomains():
        try:
            # the libvirt docs seem to indicate that the second int is for state
            # details, only used when state is ERROR, so only looking at the first
            # int returned for domain.state()
            domains[domain.name()] = DOMAIN_STATUS_ENUM[domain.state()[0]]
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                # the domain disappeared in the meantime, just ignore
                continue
            else:
                raise e

    return domains


def _find_domain(name, connection):
    '''Find whether a domain exists and get its state.

    :param str name: name of the domain to find
    :param str connection: name of libvirt connection uri
    :returns: domain state from ``DOMAIN_STATUS_ENUM`` if domain exists, or ``None`` if it doesn't
    :rtype: str or None
    '''

    conn = libvirt.openReadOnly(connection)
    try:
        domain = conn.lookupByName(name)
        return DOMAIN_STATUS_ENUM[domain.state()[0]]
    except libvirt.libvirtError as e:
        if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                # no such domain
                return None
        else:
            raise e

def _prepare_domain_list(connection=None):
    """
    Returns list of testcloud domains known to libvirt
    """
    if not connection or connection not in ["qemu:///system", "qemu:///session"]:
        try:
            domains_system = _list_domains("qemu:///system")
        except libvirt.libvirtError:
            # We can't rely on having working qemu system session
            domains_system = {}
        domains_user = _list_domains("qemu:///session")
        return {**domains_system, **domains_user}
    else:
        try:
            return _list_domains(connection)
        except libvirt.libvirtError:
            if connection not in ["qemu:///system", "qemu:///session"]:
                # We don't need logging of failures for standard qemu uris
                log.error("Connection to QEMU failed, check the connection url ( %s ) you've specified." % connection)
            return []

def find_instance(name, image=None, connection='qemu:///system'):
    """Find an instance using a given name and image, if it exists.

    Please note that ``connection`` is not taken into account when searching for the instance, but
    the instance object returned has the specified connection set. It's your responsibility to
    make sure the provided connection is valid for this instance.

    :param str name: name of instance to find
    :param image: instance of :py:class:`testcloud.image.Image`
    :param str connection: name of libvirt connection uri
    :returns: :py:class:`Instance` if the instance exists, ``None`` if it doesn't
    """

    instances = _list_instances()
    for inst in instances:
        if inst['name'] == name:
            return Instance(name, image, connection)
    return None


def list_instances(connection=None):
    """List instances known by testcloud and the state of each instance

    :param connection: libvirt compatible connection to use when listing domains
    :returns: dictionary of instance_name to domain_state mapping
    """

    domains = _prepare_domain_list(connection)
    all_instances = _list_instances()

    instances = []

    for instance in all_instances:
        if instance['name'] not in domains.keys():
            log.warn("{} is not registered, might want to delete it via 'testcloud instance clean'.".format(instance['name']))
            instance['state'] = 'de-sync'

            instances.append(instance)

        else:

            # Add the state of the instance
            instance['state'] = domains[instance['name']]

            instances.append(instance)

    return instances

def clean_instances(connection=None):
    """
    Removes all instances in 'de-sync' state.
    """
    domains = _prepare_domain_list(connection)
    all_instances = _list_instances()

    for instance in all_instances:
        if instance['name'] not in domains.keys():
            log.debug("Removing de-synced instance {}".format(instance['name']))
            instance_path = "{}/instances/{}".format(config_data.DATA_DIR, instance['name'])

            # remove from disk
            shutil.rmtree(instance_path)

class Instance(object):
    """Handles creating, starting, stopping and removing virtual machines
    defined on the local system, using an existing :py:class:`Image`.
    """

    name: str
    image: str
    connection: str
    hostname: str
    desired_arch: str
    domain_configuration: Optional[DomainConfiguration]

    def __init__(
        self,
        name="",
        image=None,
        connection="qemu:///system",
        hostname=None,
        desired_arch=platform.machine(),
        domain_configuration=None
    ):

        # Compat block for api calls without domain_configuration prepared before
        if domain_configuration:
            self.name = domain_configuration.name
            self.desired_arch = domain_configuration.system_architecture.arch
            self.ram = domain_configuration.memory_size
            self.vcpus = domain_configuration.cpu_count
            self.path = domain_configuration.path
            self.local_disk = domain_configuration.local_disk
            self.seed_path = domain_configuration.seed_path
            self.xml_path = domain_configuration.xml_path
            self.config_path = domain_configuration.config_path
            self.coreos = domain_configuration.coreos
            self.disk_number = len(domain_configuration.storage_devices)

        else:
            self.name = name
            self.desired_arch = desired_arch
            self.ram = config_data.RAM
            self.vcpus = config_data.VCPUS
            self.path = "{}/instances/{}".format(config_data.DATA_DIR, self.name)
            self.local_disk = "{}/{}-local.qcow2".format(self.path, self.name)
            self.seed_path = "{}/{}-seed.img".format(self.path, self.name)
            self.xml_path = "{}/{}-domain.xml".format(self.path, self.name)
            self.config_path = "{}/{}.ign".format(self.path, self.name)
            self.coreos = False
            self.disk_number = 1
            self.disk_size = config_data.DISK_SIZE

        self.kvm = True if (desired_arch == platform.machine() and os.path.exists("/dev/kvm")) else False
        self.image = image
        self.connection = connection
        self.pci_net = None

        self.vnc = False
        self.graphics = False
        self.hostname = hostname if hostname else config_data.HOSTNAME

        self.image_path = os.path.join(config_data.DATA_DIR, "instances", self.name, self.name + "-local.qcow2")
        self.backing_store = image.local_path if image else None
        self.mac_address = None
        self.tpm = False

        # params for cloud instance
        self.meta_path = "{}/meta".format(self.path)
        self.seed = None
        self.kernel = None
        self.initrd = None

        # params for coreos instance
        self.bu_path = "{}/{}.bu".format(self.path, self.name)
        self.ssh_path = None
        self.bu_file = None
        self.ign_file = None
        self.qemu_cmds = []
        self.domain_configuration : DomainConfiguration | None = domain_configuration if domain_configuration else None

    def prepare(self):

        """Create local directories needed to spawn the instance
        """
        # create the dirs needed for this instance
        try:
            self._create_dirs()
        except PermissionError:
            raise TestcloudPermissionsError
        if not self.coreos:
            self._create_user_data(config_data.PASSWORD)
            self._create_meta_data(self.hostname)

            # generate seed image
            self._generate_seed_image()
        else:
            # Create a dummy seed
            open(self.seed_path, 'a').close()

            if self.ign_file:
                shutil.copy(self.ign_file, self.config_path)
            else:
                self._generate_config_file()
            chcon_command = subprocess.call("chcon -t svirt_home_t %s"%self.config_path, shell=True)
            if chcon_command == 0:
                log.info("chcon command succeed ")
            else:
                log.error("chcon command failed")
                raise TestcloudInstanceError("Failure during change file SELinux security context")

        # deal with backing store
        self._create_local_disk()

    def _create_user_data(self, password, overwrite=False):
        """Save the right  password to the 'user-data' file needed to
        emulate cloud-init. Default username on cloud images is "fedora"

        Will not overwrite an existing user-data file unless
        the overwrite kwarg is set to True."""

        # Wait for tmt-1.10, replace the ugly down there with
        # file_data = config_data.USER_DATA.format(user_password=password)
        if config_data.USER_DATA.count("%s") == 1:
            file_data = config_data.USER_DATA % password
        elif config_data.USER_DATA.count("%s") == 2:
            file_data = config_data.USER_DATA % (password, password)

        data_path = '{}/meta/user-data'.format(self.path)

        if (os.path.isfile(data_path) and overwrite) or not os.path.isfile(data_path):
            with open(data_path, 'w') as user_file:
                user_file.write(file_data)
            log.debug("Generated user-data for instance {}".format(self.name))
        else:
            log.debug("user-data file already exists for instance {}. Not"
                      " regerating.".format(self.name))

    def _create_meta_data(self, hostname, overwrite=False):
        """Save the required hostname data to the 'meta-data' file needed to
        emulate cloud-init.

        Will not overwrite an existing user-data file unless
        the overwrite kwarg is set to True."""

        file_data = config_data.META_DATA % hostname

        meta_path = "{}/meta-data".format(self.meta_path)
        if (os.path.isfile(meta_path) and overwrite) or not os.path.isfile(meta_path):
            with open(meta_path, 'w') as meta_data_file:
                meta_data_file.write(file_data)

            log.debug("Generated meta-data for instance {}".format(self.name))
        else:
            log.debug("meta-data file already exists for instance {}. Not"
                      " regerating.".format(self.name))

    def _generate_seed_image(self):
        """Create a virtual filesystem needed for boot with genisoimgage on a
        given path (it should probably be somewhere in '/tmp'."""

        log.debug("creating seed image {}".format(self.seed_path))

        make_image = subprocess.call(['genisoimage',
                                      '--input-charset', 'utf-8',
                                      '--volid', 'cidata',
                                      '--joliet',
                                      '--rock',
                                      '--quiet',
                                      '--output', self.seed_path,
                                      '.',
                                      ], cwd=self.meta_path)

        # Check the subprocess.call return value for success
        if make_image == 0:
            log.info("Seed image generated successfully")
        else:
            log.error("Seed image generation failed. Exiting")
            raise TestcloudInstanceError("Failure during seed image generation")

    def _generate_config_file(self):

        if self.bu_file:
            shutil.copy(self.bu_file, self.bu_path)
        else:
            if self.ssh_path:
                with open(self.ssh_path, 'r') as inst:
                    key_content = inst.readline().strip()
            else:
                key_content = None
            # We need this weird code until the way of objects sharing with tmt gets refactored
            try:
                bu_data = config_data.COREOS_DATA % key_content
            except TypeError:
                bu_data = config_data.COREOS_DATA
            with open(self.bu_path, 'w') as user_file:
                user_file.write(bu_data)

        log.debug("creating config file {}".format(self.config_path))
        if not os.path.exists('/usr/bin/butane'):
            log.error("butane package is necessary to operate with CoreOS images")
            raise TestcloudInstanceError("butane missing")
        create_config = subprocess.call("butane --pretty --strict < %s > %s"%(self.bu_path, self.config_path), shell=True)

        # Check the subprocess.call return value for success
        if create_config == 0:
            log.info("config file created successfully")
        else:
            log.error("config file generation failed. Exiting")
            raise TestcloudInstanceError("Failure during create config file generation")

    def _create_dirs(self):
        if not os.path.isdir(self.path):
            log.debug("Creating instance directories")
            os.makedirs(self.path)
        if not os.path.isdir(self.meta_path) and not self.coreos:
                os.makedirs(self.meta_path)

    def _get_domain(self):
        """Create the connection to libvirt to control instance lifecycle.
        returns: libvirt domain object"""
        conn = libvirt.open(self.connection)
        return conn.lookupByName(self.name)

    def create_ip_file(self, ip):
        """Write the ip address found after instance creation to a file
           for easier management later. This is likely going to break
           and need a better solution."""

        with open("{}/instances/{}/ip".format(config_data.DATA_DIR,
                                              self.name), 'w') as ip_file:
            ip_file.write(ip)

    def get_instance_port(self):
        """
        Returns port of an instance
        """
        if self.connection == "qemu:///system":
            return 22 # Default SSH Port
        with open("{}/instances/{}/port".format(config_data.DATA_DIR,
                                self.name), 'r') as port_file:
            return int(port_file.readline())

    def _create_local_disk(self):
        """Create a instance using the backing store provided by Image."""

        if self.image is None:
            raise TestcloudInstanceError("attempted to access image "
                                         "information for instance {} but "
                                         "that information was not supplied "
                                         "at creation time".format(self.name))

        imgcreate_command = ['qemu-img',
                             'create',
                             '-qf',
                             'qcow2',
                             '-F',
                             'qcow2',
                             '-b',
                             self.image.local_path,
                             '-o',
                             'lazy_refcounts=on',
                             self.local_disk,
                             ]

        # make sure to expand the resultant disk if the size is set
        # Remove self.disk_size once consumers migrate to the new api
        if self.domain_configuration and not hasattr(self, "disk_size"):
            for disk in self.domain_configuration.storage_devices:
                if type(disk) == RawStorageDevice:
                    # Do not touch seed images
                    continue

                if disk.path == self.local_disk:
                    # Seed backed image (boot drive) uses a different parameters
                    imgcreate_command.append("{}G".format(disk.size))
                    subprocess.call(imgcreate_command)
                    continue

                imgcreate_command_disk = ['qemu-img', 'create', '-qf', 'qcow2', disk.path, '{}G'.format(disk.size)]
                subprocess.call(imgcreate_command_disk)
            return

        # Remove once consumers migrate to the new api
        if self.disk_size > 0:
            imgcreate_command.append("{}G".format(self.disk_size))
        subprocess.call(imgcreate_command)
        if self.disk_number > 1:
            for i in range(self.disk_number - 1):
                disk_path = "{}/{}-local{}.qcow2".format(self.path, self.name, i + 2)
                imgcreate_command_disk = ['qemu-img',
                                          'create',
                                         '-qf',
                                         'qcow2',
                                         disk_path,
                                          '{}G'.format(self.disk_size)
                                         ]
                subprocess.call(imgcreate_command_disk)

    def write_domain_xml(self):
        if self.domain_configuration:
            with open(self.xml_path, 'w') as domain_file:
                domain_file.write(self.domain_configuration.generate())
            return

        domain_configuration = DomainConfiguration(self.name)
        domain_configuration.cpu_count = self.vcpus
        domain_configuration.memory_size = self.ram * 1024

        if self.desired_arch == "x86_64":
            domain_configuration.system_architecture = X86_64ArchitectureConfiguration(kvm=self.kvm, uefi=config_data.UEFI, model="q35")
        elif self.desired_arch == "aarch64":
            domain_configuration.system_architecture = AArch64ArchitectureConfiguration(kvm=self.kvm, uefi=True, model="virt")
        elif self.desired_arch == "ppc64le":
            domain_configuration.system_architecture = Ppc64leArchitectureConfiguration(kvm=self.kvm, uefi=False, model="pseries")
        elif self.desired_arch == "s390x":
            domain_configuration.system_architecture = S390xArchitectureConfiguration(kvm=self.kvm, uefi=False, model="s390-ccw-virtio")
        else:
            raise TestcloudInstanceError("Unsupported arch")

        mac_address = self.mac_address or util.generate_mac_address()
        if self.connection == "qemu:///system":
            domain_configuration.network_configuration = SystemNetworkConfiguration(mac_address=mac_address)
        elif self.connection == "qemu:///session":
            port = util.spawn_instance_port_file(self.name)
            device_type = "virtio-net-pci" if not util.needs_legacy_net(self.image.name) else "e1000"
            domain_configuration.network_configuration = UserNetworkConfiguration(mac_address=mac_address, port=port, device_type=device_type)
        else:
            raise TestcloudInstanceError("Unsupported connection type")

        image = QCow2StorageDevice(self.local_disk)
        domain_configuration.storage_devices.append(image)

        if self.coreos:
            domain_configuration.coreos = True
            domain_configuration.qemu_args.extend(config_data.CMD_LINE_ARGS_COREOS)
            domain_configuration.qemu_envs.update(config_data.CMD_LINE_ENVS_COREOS)
        else:
            domain_configuration.qemu_args.extend(config_data.CMD_LINE_ARGS)
            domain_configuration.qemu_envs.update(config_data.CMD_LINE_ENVS)
            seed_disk = RawStorageDevice(self.seed_path)
            domain_configuration.storage_devices.append(seed_disk)

        if self.tpm:
            domain_configuration.tpm_configuration = TPMConfiguration()

        if self.disk_number > 1:
            for i in range(self.disk_number - 1):
                additional_disk_path = "{}/{}-local{}.qcow2".format(self.path, self.name, i + 2)
                domain_configuration.storage_devices.append(QCow2StorageDevice(additional_disk_path))

        with open(self.xml_path, 'w') as domain_file:
            domain_file.write(domain_configuration.generate())

    def spawn_vm(self):
        """Create and boot the instance, using prepared data."""

        self.write_domain_xml()

        with open(self.xml_path, 'r') as xml_file:
            domain_xml = ''.join([x for x in xml_file.readlines()])
        conn = libvirt.open(self.connection)
        conn.defineXML(domain_xml)

    def expand_qcow(self, size="+10G"):
        """Expand the storage for a qcow image. Currently unused."""

        log.info("expanding qcow2 image {}".format(self.image_path))
        subprocess.call(['qemu-img',
                         'resize',
                         self.image_path,
                         size])

        log.info("Resized image...")
        return

    def boot(self, timeout=config_data.BOOT_TIMEOUT):
        """Deprecated alias for :py:meth:`start`"""

        log.warn("instance.boot has been depricated and will be removed in a "
                 "future release, use instance.start instead")

        self.start(timeout)

    def start(self, timeout=config_data.BOOT_TIMEOUT):
        """Start an existing instance and wait up to :py:attr:`timeout` seconds
        for a network interface to appear.

        :param int timeout: number of seconds to wait before timing out.
                            Setting this to 0 will disable timeout, default
                            is configured with :py:const:`BOOT_TIMEOUT` config
                            value.
        :raises TestcloudInstanceError: if there is an error while creating the
                                        instance or if the timeout is reached
                                        while looking for a network interface
        """

        log.debug("Creating instance {}".format(self.name))
        dom = self._get_domain()
        try:
            create_status = dom.create()
        except libvirt.libvirtError:
            log.warning("Instance startup failed, retrying in 5 seconds...")
            time.sleep(5)
            create_status = dom.create()

        # libvirt doesn't directly raise errors on boot failure, check the
        # return code to verify that the boot process was successful from
        # libvirt's POV
        if create_status != 0:
            raise TestcloudInstanceError("Instance {} did not start "
                                         "successfully, see libvirt logs for "
                                         "details".format(self.name))
        log.info("Polling instance for active network interface")

        poll_tick = 0.5
        timeout_ticks = timeout / poll_tick
        count = 0
        port_open = 1

        # poll libvirt for domain interfaces, returning when an interface is
        # found, indicating that the boot process is post-cloud-init
        while count <= timeout_ticks:
            if self.connection == "qemu:///system":
                domif = dom.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE)
            elif self.connection == "qemu:///session":
                domif = {}
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                port_open = sock.connect_ex(('127.0.0.1',self.get_instance_port()))
            else:
                # We dont know what to do with other connection types yet! TODO: Find out, refactor
                raise TestcloudInstanceError("We currently don't support connections other than"
                                             "qemu:///system and qemu:///session")

            if len(domif) > 0 or timeout_ticks == 0 or port_open == 0:
                log.info("Successfully booted instance {}".format(self.name))
                return

            count += 1
            time.sleep(poll_tick)

        # If we get here, the boot process has timed out
        raise TestcloudInstanceError("Instance {} has failed to boot in {} "
                                     "seconds".format(self.name, timeout))

    def stop(self, soft=False):
        """Stop the instance
        Uses graceful shutdown when soft is True, destroys the vm otherwise

        :raises TestcloudInstanceError: if the instance does not exist or
                                        if unable to stop the instance (host is busy)
        """

        log.debug("stopping instance {}.".format(self.name))

        domain_state = _find_domain(self.name, self.connection)

        if domain_state is None:
            raise TestcloudInstanceError("Instance doesn't exist: {}".format(self.name))

        if domain_state == 'shutoff':
            log.debug('Instance already shut off, not stopping: {}'.format(self.name))
            return

        retries = config_data.STOP_RETRIES

        while retries > 0:
            try:
                # stop (destroy) the vm
                if not soft:
                    self._get_domain().destroy()
                else:
                    while _find_domain(self.name, self.connection) != "shutoff" and retries > 0:
                        retries -= 1
                        log.debug("Shutting down the domain (%d retries left)" % (retries))
                        self._get_domain().shutdown()
                        time.sleep(5)
                    if _find_domain(self.name, self.connection) != "shutoff":
                        raise TestcloudInstanceError('Failed to shutdown the guest gracfully after {} attempts.'
                                                    .format(config_data.STOP_RETRIES))
                return
            except libvirt.libvirtError as e:
                if e.get_error_code() == libvirt.VIR_ERR_SYSTEM_ERROR:
                    # host is busy, see https://bugzilla.redhat.com/1205647#c13
                    log.warn("Host is busy, retrying to stop the instance {}".format(self.name))
                elif e.get_error_code() == libvirt.VIR_ERR_OPERATION_INVALID:
                    log.debug("Domain stopped between attempts, ignoring error: {}".format(e))
                    return
                else:
                    raise TestcloudInstanceError('Error while stopping instance {}: {}'
                                                 .format(self.name, e))

            retries -= 1
            time.sleep(config_data.STOP_RETRY_WAIT)

        raise TestcloudInstanceError("Unable to stop instance {}.".format(self.name))

    def reboot(self, soft=True):
        """Reboots the instance
        Uses graceful shutdown when soft is True, destroys the vm otherwise

        :raises TestcloudInstanceError: if the instance does not exist or
                                        if unable to stop the instance (host is busy)
        """
        self.stop(soft=soft)
        self.start()

    def _remove_from_disk(self):
        log.debug("removing instance {} from disk".format(self.path))
        shutil.rmtree(self.path)

    def _remove_from_libvirt(self):
        # remove from libvirt, assuming that it's stopped already
        domain_state = _find_domain(self.name, self.connection)
        if domain_state is not None:
            log.debug("Unregistering instance from libvirt.")
            self._get_domain().undefineFlags(libvirt.VIR_DOMAIN_UNDEFINE_NVRAM)
        else:
            log.warn('Instance "{}" not found in libvirt "{}". Was it removed already? Should '
                     'you have used a different connection?'.format(self.name, self.connection))

    def remove(self, autostop=True):
        """Remove an already stopped instance

        :param bool autostop: if the instance is running, stop it first
        :raises TestcloudInstanceError: if the instance does not exist, or is still
                                        running and ``autostop==False``
        """

        log.debug("removing instance {} from libvirt.".format(self.name))

        # this should be changed if/when we start supporting configurable
        # libvirt connections
        domain_state = _find_domain(self.name, self.connection)

        if domain_state == 'running':
            if autostop:
                self.stop()
            else:
                raise TestcloudInstanceError(
                    "Cannot remove running instance {}. Please stop the "
                    "instance before removing or use '-f' parameter.".format(self.name))

        self._remove_from_libvirt()
        self._remove_from_disk()

    def destroy(self):
        '''A deprecated method. Please call :meth:`remove` instead.'''

        log.debug('DEPRECATED: destroy() method was deprecated. Please use remove()')
        self.remove()

    def get_ip(self, timeout=60, domain=None):
        '''Retrieve IP address of the instance (the first one, if there are
        multiple).

        :param int timeout: how long to wait if IP address is not yet ready
            (e.g. when booting), in seconds
        :param libvirt.domain domain: the domain object to use, instead of
            using the domain associated with this instance. This is for
            backwards compatibility only and will be removed in the future.
        :return: IP address of the instance (or IP:port)
        :rtype: str
        :raises TestcloudInstanceError: when time runs out and no IP is
            assigned
        '''

        domain = domain or self._get_domain()
        counter = 0
        sleep_interval = 0.5

        while counter <= timeout:
            try:
                if self.connection == "qemu:///system":
                    output = domain.interfaceAddresses(
                        libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE)
                else:
                    # Return early for qemu user session
                    return "127.0.0.1"
                # example output:
                # {'vnet0': {'addrs': [{'addr': '192.168.11.33', 'prefix': 24, 'type': 0}],
                #  'hwaddr': '52:54:00:54:4b:b4'}}
                if output:
                    addrs = [ addr['addr'] for iface in output.values()
                              for addr in iface.get('addrs', [])
                              if 'addr' in addr ]
                    if addrs:
                        return addrs[0]
            except libvirt.libvirtError as e:
                if e.get_error_code() == libvirt.VIR_ERR_OPERATION_INVALID:
                    # the domain is not yet running
                    pass
                else:
                    raise e
            counter += sleep_interval
            time.sleep(sleep_interval)

        msg = "Couldn't find IP for %s before %s second timeout" % (domain,
              timeout)
        log.warn(msg)
        raise TestcloudInstanceError(msg)

    def prepare_vagrant_init(self, prepare_command):
        log.warn('Support for images without cloud-init in testcloud is not reliable. You have been warned...')
        if self.connection == "qemu:///session":
            log.info("Giving the VM some time (%s seconds) to boot up..." % config_data.VAGRANT_USER_SESSION_WAIT)
            time.sleep(config_data.VAGRANT_USER_SESSION_WAIT)
        log.debug("Adjusting the image to support cloud-init...")
        conn = libvirt.open(self.connection)
        stream = conn.newStream(libvirt.VIR_STREAM_NONBLOCK)
        dom = conn.lookupByName(self.name)
        console = dom.openConsole(None, stream, 0)
        username_formatted = "%s\n" % config_data.VAGRANT_USER
        password_formatted = "%s\n" % config_data.VAGRANT_PASS
        time.sleep(10)
        stream.send(username_formatted.encode())
        time.sleep(5)
        stream.send(password_formatted.encode())
        time.sleep(5)
        stream.send(prepare_command.encode())
        time.sleep(8)
        stream.finish()

    def set_seed(self, path):
        """Set the seed image for the instance."""
        self.seed = path
