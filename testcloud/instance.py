# -*- coding: utf-8 -*-
# Copyright 2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""
Representation of a Testcloud spawned (or to-be-spawned) virtual machine
"""

import os
import sys
import re
import subprocess
import glob
import logging
import time

import libvirt
import shutil
import uuid
import jinja2
import platform
import socket

try:
    import guestfs
except ImportError:
    pass # We'll lose guest detection ( https://bugzilla.redhat.com/show_bug.cgi?id=1075594 )

from . import config
from . import util
from .exceptions import TestcloudInstanceError, TestcloudPermissionsError

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

    def __init__(
        self,
        name,
        image=None,
        connection='qemu:///system',
        hostname=None,
        desired_arch=platform.machine(),
        kvm=True
    ):

        self.name = name
        self.desired_arch = desired_arch
        self.kvm = True if (desired_arch == platform.machine() and os.path.exists("/dev/kvm")) else False
        self.path = "{}/instances/{}".format(config_data.DATA_DIR, self.name)
        self.image = image
        self.connection = connection
        self.local_disk = "{}/{}-local.qcow2".format(self.path, self.name)
        self.xml_path = "{}/{}-domain.xml".format(self.path, self.name)
        self.ram = config_data.RAM
        self.vcpus = config_data.VCPUS
        self.pci_net = None
        # desired size of disk, in GiB
        self.disk_size = config_data.DISK_SIZE
        self.vnc = False
        self.graphics = False
        self.hostname = hostname if hostname else config_data.HOSTNAME

        self.image_path = os.path.join(config_data.DATA_DIR, "instances", self.name, self.name + "-local.qcow2")
        self.backing_store = image.local_path if image else None
        # params for cloud instance
        self.meta_path = "{}/meta".format(self.path)
        self.seed_path = "{}/{}-seed.img".format(self.path, self.name)
        self.seed = None
        self.kernel = None
        self.initrd = None
        # params for coreos instance
        self.config_path = "{}/{}.ign".format(self.path, self.name)
        self.bu_path = "{}/{}.bu".format(self.path, self.name)
        self.ssh_path = None
        self.bu_file = None
        self.ign_file = None
        self.coreos = False

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
            if not self.coreos:
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

    def create_port_file(self, port):
        """Write the port address found before instance creation to a file
           for easier management later. This is likely going to break
           and need a better solution."""

        with open("{}/instances/{}/port".format(config_data.DATA_DIR,
                                              self.name), 'w') as port_file:
            port_file.write(str(port))

    def get_instance_port(self):
        """
        Returns port of an instance
        """
        if self.connection == "qemu:///system":
            return 22 # Default SSH Port
        with open("{}/instances/{}/port".format(config_data.DATA_DIR,
                                self.name), 'r') as port_file:
            return int(port_file.readline())

    def check_port_available(self, port):
        """
        Checks is a port is available for use
        Returns True/False
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        if result != 0:
            return True
        return False

    def find_next_usable_port(self):
        """
        Returns next usable port for user session vm, starting with SSH_USER_PORT_BASE
        Tries to recycle freed ports from currently used interval
        """
        used_ports = []
        for dir in os.listdir("{}/instances/".format(config_data.DATA_DIR)):
            try:
                with open("{}/instances/{}/port".format(config_data.DATA_DIR,
                                                dir), 'r') as port_file:
                    used_ports.append(int(port_file.readline()))
            except FileNotFoundError:
                continue

        if len(used_ports) == 0:
            used_ports.append(config_data.SSH_USER_PORT_BASE)
        available_in_interval = [i for i in range(config_data.SSH_USER_PORT_BASE,max(used_ports))]
        if len(available_in_interval) > 0:
            i = 0
            recycleable_ports = [item for item in available_in_interval if item not in used_ports]
            length = len(recycleable_ports)
            if length > 0:
                while i < length:
                    if self.check_port_available(recycleable_ports[i]):
                        return recycleable_ports[i]
                    else:
                        i = i + 1

        next_port = max(used_ports) + 1
        while not self.check_port_available(next_port):
            next_port = next_port + 1

        return next_port

    def _needs_legacy_net(self):
        """
        Returns True when the use of e1000 pci network adapter is required
        Returns False when condition to use the legacy net is not met
        Returns None when detection failed
        Otherwise, usage of virtio-net-pci is a preferred choice
        """
        try:
            guestfs
        except NameError:
            log.warning("Python libguestfs bindings are missing, guest detection won't work properly!")
            # Try a bit harder
            if not self.image.name:
                # If, for some reason, we don't have image.name, we can't guess anything
                return None
            # el 7 in image name means we need legacy net
            if re.search(r'(rhel|centos).*-7', self.image.name.lower()):
                return True
            # false otherwise
            return False

        g = guestfs.GuestFS(python_return_dict=True)
        g.add_drive_opts(self.local_disk, readonly=1)

        try:
            g.launch()
            roots = g.inspect_os()
        except RuntimeError:
            return None

        if not roots:
            return None

        if g.inspect_get_distro(roots[0]) in ["rhel", "centos"] and g.inspect_get_major_version(roots[0]) == 7:
            return True

        return False

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
        if self.disk_size > 0:
            imgcreate_command.append("{}G".format(self.disk_size))
        subprocess.call(imgcreate_command)


    def write_domain_xml(self):
        """Load the default xml template, and populate it with the following:
         - name
         - uuid
         - locations of disks
         - network mac address
        """

        # Set up the jinja environment
        jinjaLoader = jinja2.FileSystemLoader(searchpath=[config.DEFAULT_CONF_DIR,
                                                          config_data.DATA_DIR])
        jinjaEnv = jinja2.Environment(loader=jinjaLoader)

        # Make a copy of qemu args from config_object so we don't get to a shitty state when creating a bunch of vms
        qemu_args = config_data.CMD_LINE_ARGS.copy()

        # Configuration for all supported architectures
        model_map = {
            "x86_64":
                {
                    "model": "pc",
                    "cpu_kvm": '<cpu mode="host-passthrough" check="none" migratable="on"/>',
                    "cpu_qemu": '<cpu mode="custom" match="exact"><model>qemu64</model></cpu>',
                    "qemu": "qemu-system-x86_64",
                    "extra_specs":
                    """
                        <features><acpi/><apic/><vmport state='off'/></features>
                        <pm><suspend-to-mem enabled='no'/><suspend-to-disk enabled='no'/></pm>
                        <memballoon model='virtio'>
                        <address type='pci' domain='0x0000' bus='0x00' slot='0x04' function='0x0'/>
                        </memballoon>
                    """
                },
            "ppc64le":
                {
                    "model": "pseries-5.1",
                    "cpu_kvm": '<cpu mode="host-passthrough" check="none"/>',
                    "cpu_qemu": '<cpu mode="custom" match="exact" check="none"><model fallback="forbid">POWER9</model></cpu>',
                    "qemu": "qemu-system-ppc64",
                    "extra_specs":
                    """
                        <memballoon model='virtio'>
                        <address type='pci' domain='0x0000' bus='0x00' slot='0x04' function='0x0'/>
                        </memballoon>
                    """
                },
            "aarch64":
                {
                    "model": "virt",
                    "cpu_kvm": '<cpu mode="host-passthrough" check="none"/>',
                    "cpu_qemu": '<cpu mode="custom" match="exact"><model>cortex-a57</model></cpu>',
                    "qemu": "qemu-system-aarch64",
                    "extra_specs":
                    """
                        <features><acpi/><gic/></features>
                        <memballoon model='virtio'>
                        <address type='pci' domain='0x0000' bus='0x00' slot='0x04' function='0x0'/>
                        </memballoon>
                    """
                },
            "s390x":
                {
                    "model": "s390-ccw-virtio-6.1",
                    "cpu_kvm": '<cpu mode="host-passthrough" check="none"/>',
                    "cpu_qemu": '<cpu mode="custom" match="exact"><model>qemu</model></cpu>',
                    "qemu": "qemu-system-s390x",
                    "extra_specs":
                    """
                    """
                }
        }


        if platform.machine() not in model_map:
            log.error("Unsupported architecture, architectures supported by testcloud are: %s." % model_map.keys())
            raise TestcloudInstanceError()

        # We need to shuffle things around network setup a bit if we're running in qemu:///session instead of qemu:///system
        if self.connection == "qemu:///session":
            network_type = "user"
            network_source = ""
            ip_setup = "<ip family='ipv4' address='172.17.2.0' prefix='24'/>"
            log.info("Adding another network device for ssh from host...")
            lock = util.Filelock()
            with lock:
                port = self.find_next_usable_port()
                self.create_port_file(port)
            if self.pci_net:
                device_type = self.pci_net
            else:
                device_type = "virtio-net-pci" if not self._needs_legacy_net() else "e1000"
            network_args = ["-netdev", "user,id=testcloud_net.{},hostfwd=tcp::{}-:22".format(port, port),
                            "-device", "{},addr=1e.0,netdev=testcloud_net.{}".format(device_type, port)]
            qemu_args.extend(network_args)
        else:
            network_type = "network"
            network_source = "<source network='default'/>"
            ip_setup = ""

        # Stuff our values in a dict
        args_envs = ""
        instance_values = {'domain_name': self.name,
                           'uuid': uuid.uuid4(),
                           'memory': self.ram * 1024,  # MiB to KiB
                           'vcpus': self.vcpus,
                           'disk': self.local_disk,
                           'mac_address': util.generate_mac_address(),
                           'uefi_loader': "",
                           'emulator_path': "", # Required, will be determined later
                           'arch': self.desired_arch,
                           'virt_type': "kvm" if self.kvm else "qemu",
                           'model': model_map[self.desired_arch]["model"],
                           'cpu': model_map[self.desired_arch]["cpu_kvm"] if self.kvm else model_map[self.desired_arch]["cpu_qemu"],
                           'extra_specs': model_map[self.desired_arch]["extra_specs"],
                           'network_type': network_type,
                           'network_source': network_source,
                           "ip_setup": ip_setup}

        instance_values["model"] = model_map[self.desired_arch]["model"]

        xml_template = jinjaEnv.get_template(config_data.XML_TEMPLATE)
        instance_values['seed'] = self.seed_path
        if self.coreos:
            if config_data.CMD_LINE_ARGS_COREOS or config_data.CMD_LINE_ENVS_COREOS:
                cmdline_args = config_data.CMD_LINE_ARGS_COREOS + ['name=opt/com.coreos/config,file=%s'%self.config_path, ]
                for qemu_arg in cmdline_args:
                    args_envs += "    <qemu:arg value='%s'/>\n" % qemu_arg

                for qemu_env in config_data.CMD_LINE_ENVS_COREOS:
                    args_envs += "    <qemu:env name='%s' value='%s'/>\n" % (qemu_env, config_data.CMD_LINE_ENVS_COREOS[qemu_env])

        if qemu_args or config_data.CMD_LINE_ENVS:
            for qemu_arg in qemu_args:
                args_envs += "    <qemu:arg value='%s'/>\n" % qemu_arg

            for qemu_env in config_data.CMD_LINE_ENVS:
                args_envs += "    <qemu:env name='%s' value='%s'/>\n" % (qemu_env, config_data.CMD_LINE_ENVS[qemu_env])
        args_envs = "  <qemu:commandline>\n" + args_envs + " </qemu:commandline>"
        instance_values["qemu_args"] = args_envs
        if config_data.UEFI:
            instance_values["uefi_loader"] = "<loader readonly='yes' type='pflash'>/usr/share/edk2/ovmf/OVMF_CODE.fd</loader>"

        if self.desired_arch == "aarch64":
            instance_values["uefi_loader"] = "<loader readonly='yes' type='pflash'>/usr/share/edk2/aarch64/QEMU_EFI-silent-pflash.raw</loader>"

        # Try to query usable qemu binaries for desired architecture
        qemu_paths = ["/usr/bin/%s" % model_map[self.desired_arch]["qemu"], "/usr/libexec/%s" % model_map[self.desired_arch]["qemu"]]
        instance_values["emulator_path"] = None

        for path in qemu_paths:
            instance_values["emulator_path"] = path if os.path.exists(path) else instance_values["emulator_path"]

        # Some systems might only have qemu-kvm as the qemu binary, try that if everything else failed...
        if not instance_values["emulator_path"] and self.kvm:
            for path in ["/usr/bin/qemu-kvm", "/usr/libexec/qemu-kvm"]:
                instance_values["emulator_path"] = path if os.path.exists(path) else instance_values["emulator_path"]

        if not instance_values["emulator_path"]:
            raise TestcloudInstanceError("No usable qemu binary exist, tried: %s" % qemu_paths)

        # Write out the final xml file for the domain
        with open(self.xml_path, 'w') as dom_template:
            dom_template.write(xml_template.render(instance_values))

        return

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
        log.debug("Polling instance for active network interface")

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

    def prepare_vagrant_init(self):
        log.warn('Support for images without cloud-init in testcloud is not reliable. You have been warned...')
        if self.connection == "qemu:///session":
            log.debug("Giving the VM some time (%s seconds) to boot up..." % config_data.VAGRANT_USER_SESSION_WAIT)
            time.sleep(config_data.VAGRANT_USER_SESSION_WAIT)
        log.debug("Adjusting the image to support cloud-init...")
        conn = libvirt.open(self.connection)
        stream = conn.newStream(libvirt.VIR_STREAM_NONBLOCK)
        dom = conn.lookupByName(self.name)
        console = dom.openConsole(None, stream, 0)
        username_formatted = "%s\n" % config_data.COS_VAG_USER
        password_formatted = "%s\n" % config_data.COS_VAG_PASS
        time.sleep(10)
        stream.send(username_formatted.encode())
        time.sleep(5)
        stream.send(password_formatted.encode())
        time.sleep(5)
        stream.send(b"dnf -y install cloud-init && cloud-init init && reboot\n")
        time.sleep(8)
        stream.finish()

    def set_seed(self, path):
        """Set the seed image for the instance."""
        self.seed = path
