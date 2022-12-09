from typing import Optional
import string
import xml.dom.minidom
import os
import uuid

from .exceptions import TestcloudInstanceError


class ArchitectureConfiguration():
    qemu:str
    arch:str
    model:str
    kvm: bool
    def generate(self) -> str:
        raise NotImplementedError()


class X86_64ArchitectureConfiguration(ArchitectureConfiguration):
    qemu = "qemu-system-x86_64"
    arch = "x86_64"
    model = "q35"
    def __init__(self, kvm=True, uefi=False) -> None:
        self.kvm = kvm
        self.uefi = uefi

    def generate(self):
        return """
        <os>
            <type arch='{arch}' machine='{model}'>hvm</type>
            {uefi_loader}
            <boot dev='hd'/>
        </os>
        {cpu}
        <features>
            <acpi/>
            <apic/>
            <vmport state='off'/>
        </features>
        <pm>
            <suspend-to-mem enabled='no'/>
            <suspend-to-disk enabled='no'/>
        </pm>
        <memballoon model='virtio'></memballoon>
        """.format(
            arch=self.arch,
            model=self.model,
            uefi_loader="<loader readonly='yes' type='pflash'>/usr/share/edk2/ovmf/OVMF_CODE.fd</loader>" if self.uefi else "",
            cpu="<cpu mode='host-passthrough' check='none' migratable='on'/>" if self.kvm else "<cpu mode='custom' match='exact'><model>qemu64</model></cpu>",
        )


class AArch64ArchitectureConfiguration(ArchitectureConfiguration):
    qemu = "qemu-system-aarch64"
    arch = "aarch64"
    model = "virt"
    def __init__(self, kvm=True) -> None:
        self.kvm = kvm

    def generate(self) -> str:
        return """
        <os>
            <type arch='{arch}' machine='{model}'>hvm</type>
            {uefi_loader}
            <boot dev='hd'/>
        </os>
        {cpu}
        <features>
            <acpi/>
            <gic/>
        </features>
        <memballoon model='virtio'></memballoon>
        """.format(
            arch=self.arch,
            model=self.model,
            uefi_loader="<loader readonly='yes' type='pflash'>/usr/share/edk2/aarch64/QEMU_EFI-silent-pflash.raw</loader>",
            cpu="<cpu mode='host-passthrough' check='none'/>" if self.kvm else "<cpu mode='custom' match='exact'><model>cortex-a57</model></cpu>",
        )


class Ppc64leArchitectureConfiguration(ArchitectureConfiguration):
    qemu = "qemu-system-ppc64"
    arch = "ppc64le"
    model = "pseries"
    def __init__(self, kvm=True) -> None:
        self.kvm = kvm

    def generate(self) -> str:
        return """
        <os>
            <type arch='{arch}' machine='{model}'>hvm</type>
            <boot dev='hd'/>
        </os>
        {cpu}
        <memballoon model='virtio'></memballoon>
        """.format(
            arch=self.arch,
            model=self.model,
            cpu="<cpu mode='host-passthrough' check='none'/>" if self.kvm else "<cpu mode='custom' match='exact' check='none'><model fallback='forbid'>POWER9</model></cpu>"
        )


class S390xArchitectureConfiguration(ArchitectureConfiguration):
    qemu = "qemu-system-s390x"
    arch = "s390x"
    model = "s390-ccw-virtio"
    def __init__(self, kvm=True) -> None:
        self.kvm = kvm

    def generate(self) -> str:
        return """
        <os>
            <type arch='{arch}' machine='{model}'>hvm</type>
            <boot dev='hd'/>
        </os>
        {cpu}
        """.format(
            arch=self.arch,
            model=self.model,
            cpu="<cpu mode='host-passthrough' check='none'/>" if self.kvm else "<cpu mode='custom' match='exact'><model>qemu</model></cpu>"
        )



def storage_device_name_generator():
    prefix = "vd"
    for i in range(26):
        yield prefix + string.ascii_lowercase[i]
storage_device_name = storage_device_name_generator()


class StorageDeviceConfiguration():
    def __init__(self) -> None:
        pass

    def generate(self) -> str:
        raise NotImplementedError()


class RawStorageDevice(StorageDeviceConfiguration):
    def __init__(self, path) -> None:
        self.path = path

    def generate(self):
        return """
        <disk type='file' device='disk'>
            <driver name='qemu' type='raw'/>
            <source file="%s"/>
            <target dev='%s' bus='virtio'/>
        </disk>
        """ % (
            self.path,
            next(storage_device_name),
        )


class QCow2StorageDevice(StorageDeviceConfiguration):
    def __init__(self, path) -> None:
        self.path = path

    def generate(self):
        return """
        <disk type='file' device='disk'>
            <driver name='qemu' type='qcow2' cache='unsafe'/>
            <source file="%s"/>
            <target dev='%s' bus='virtio'/>
        </disk>
        """ % (
            self.path,
            next(storage_device_name),
        )


class NetworkConfiguration():
    mac_address : str
    additional_qemu_args : list[str]
    def __init__(self) -> None:
        self.mac_address = ""
        self.additional_qemu_args = []
    def generate(self) -> str:
        raise NotImplementedError()


class SystemNetworkConfiguration(NetworkConfiguration):
    def __init__(self, mac_address) -> None:
        super().__init__()
        self.mac_address = mac_address

    def generate(self):
        return """
        <interface type='network'>
            <mac address="{mac_address}"/>
            <source network='default'/>
            <model type='virtio'/>
        </interface>
        """.format(
            mac_address=self.mac_address,
        )


class UserNetworkConfiguration(NetworkConfiguration):
    def __init__(self, mac_address, port=6666, device_type="virtio-net-pci") -> None:
        super().__init__()
        self.mac_address = mac_address
        self.additional_qemu_args = ["-netdev", "user,id=testcloud_net.{},hostfwd=tcp::{}-:22".format(port, port),
                                     "-device", "{},addr=1e.0,netdev=testcloud_net.{}".format(device_type, port)]

    def generate(self):
        return """
        <interface type='user'>
            <mac address="{mac_address}"/>
            <ip family='ipv4' address='172.17.2.0' prefix='24'/>
            <model type='virtio'/>
        </interface>
        """.format(
            mac_address=self.mac_address,

        )


class TPMConfiguration():
    def __init__(self) -> None:
        pass

    def generate(self):
        return """
        <tpm model='tpm-tis'>
            <backend type='emulator' version='2.0'/>
        </tpm>
        """


class DomainConfiguration():
    name : str
    cpu_count : int
    memory_size : int
    system_architecture: Optional[ArchitectureConfiguration]
    storage_devices: list[StorageDeviceConfiguration]
    network_configuration: Optional[NetworkConfiguration]
    tpm_configuration: Optional[TPMConfiguration]
    qemu_args: list[str]
    qemu_envs: dict[str, str]

    def __init__(self) -> None:
        self.uuid = uuid.uuid4()
        self.name = ""
        self.cpu_count = -1
        self.memory_size = -1
        self.system_architecture = None
        self.storage_devices = []
        self.network_configuration = None
        self.tpm_configuration = None
        self.qemu_args = []
        self.qemu_envs = {}

    def generate_storage_devices(self) -> str:
        return "\n".join([device.generate() for device in self.storage_devices])

    def get_emulator(self) -> str:
        assert self.system_architecture is not None
        qemu_paths = [
            # Try to query usable qemu binaries for desired architecture
            "/usr/bin/" + self.system_architecture.qemu,
            "/usr/libexec/" + self.system_architecture.qemu,
            # Some systems might only have qemu-kvm as the qemu binary, try that if everything else failed...
            "/usr/bin/qemu-kvm",
            "/usr/libexec/qemu-kvm"
        ]
        for path in qemu_paths:
            if os.path.exists(path):
                return path

        raise TestcloudInstanceError("No usable qemu binary exist, tried: %s" % qemu_paths)

    def get_qemu_args(self) -> str:
        assert self.network_configuration is not None
        self.qemu_args.extend(self.network_configuration.additional_qemu_args)
        return "\n".join(["<qemu:arg value='%s'/>" % qemu_arg for qemu_arg in self.qemu_args])

    def get_qemu_envs(self) -> str:
        return "\n".join(["<qemu:env name='%s' value='%s'/>" % (qemu_env, self.qemu_envs[qemu_env]) for qemu_env in self.qemu_envs])

    def generate(self) -> str:
        assert self.system_architecture is not None
        assert self.network_configuration is not None

        domain_xml = """
        <domain type='{virt_type}' xmlns:qemu='http://libvirt.org/schemas/domain/qemu/1.0'>
            <name>{domain_name}</name>
            <uuid>{uuid}</uuid>
            <memory unit='KiB'>{memory}</memory>
            <currentMemory unit='KiB'>{memory}</currentMemory>
            <vcpu placement='static'>{vcpus}</vcpu>
            {system_architecture}
            <clock offset='utc'>
                <timer name='rtc' tickpolicy='catchup'/>
                <timer name='pit' tickpolicy='delay'/>
                <timer name='hpet' present='no'/>
            </clock>
            <on_poweroff>destroy</on_poweroff>
            <on_reboot>restart</on_reboot>
            <on_crash>restart</on_crash>
            <devices>
                <emulator>{emulator_path}</emulator>
                {storage_devices}
                {network_configuraton}
            </devices>
            <serial type='pty'>
                <target port='0'/>
            </serial>
            <console type='pty'>
                <target type='serial' port='0'/>
            </console>
            <input type="keyboard" bus="virtio"/>
            <rng model='virtio'>
                <backend model='random'>/dev/urandom</backend>
            </rng>
            {tpm}
            <qemu:commandline>
                {qemu_args}
                {qemu_envs}
            </qemu:commandline>
        </domain>
        """.format(
            virt_type="kvm" if self.system_architecture.kvm else "qemu",
            domain_name=self.name,
            uuid=self.uuid,
            memory=self.memory_size,
            vcpus=self.cpu_count,
            system_architecture=self.system_architecture.generate(),
            emulator_path=self.get_emulator(),
            storage_devices=self.generate_storage_devices(),
            network_configuraton=self.network_configuration.generate(),
            tpm=self.tpm_configuration.generate() if self.tpm_configuration else "",
            qemu_args=self.get_qemu_args(),
            qemu_envs=self.get_qemu_envs(),
        )
        almost_pretty_xml = xml.dom.minidom.parseString(domain_xml).toprettyxml(indent="  ")
        return os.linesep.join([s for s in almost_pretty_xml.splitlines() if s.strip()])
