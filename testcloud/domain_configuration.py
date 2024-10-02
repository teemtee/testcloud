from typing import Optional
import string
import xml.dom.minidom
import os
import uuid
import platform

from testcloud.exceptions import TestcloudInstanceError
from testcloud import config
from testcloud import util
from testcloud import image

config_data = config.get_config()


class ArchitectureConfiguration:
    qemu: str
    arch: str
    model: str
    kvm: bool

    def generate(self) -> str:
        raise NotImplementedError()


class X86_64ArchitectureConfiguration(ArchitectureConfiguration):
    qemu = "qemu-system-x86_64"
    arch = "x86_64"
    model = "q35"

    def __init__(self, kvm=True, uefi=False, model="q35") -> None:
        self.kvm = kvm
        self.uefi = uefi
        self.model = model

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
            cpu=(
                "<cpu mode='host-passthrough' check='none' migratable='on'/>"
                if self.kvm
                else "<cpu mode='custom' match='exact'><model>qemu64</model></cpu>"
            ),
        )


class AArch64ArchitectureConfiguration(ArchitectureConfiguration):
    qemu = "qemu-system-aarch64"
    arch = "aarch64"
    model = "virt"

    def __init__(self, kvm=True, uefi=True, model="virt") -> None:
        self.kvm = kvm
        self.uefi = uefi
        self.model = model

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
            cpu=(
                "<cpu mode='host-passthrough' check='none'/>"
                if self.kvm
                else "<cpu mode='custom' match='exact'><model>cortex-a57</model></cpu>"
            ),
        )


class Ppc64leArchitectureConfiguration(ArchitectureConfiguration):
    qemu = "qemu-system-ppc64"
    arch = "ppc64le"
    model = "pseries"

    def __init__(self, kvm=True, uefi=False, model="pseries") -> None:
        self.kvm = kvm
        self.uefi = uefi
        self.model = model

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
            cpu=(
                "<cpu mode='host-passthrough' check='none'/>"
                if self.kvm
                else "<cpu mode='custom' match='exact' check='none'><model fallback='forbid'>POWER9</model></cpu>"
            ),
        )


class S390xArchitectureConfiguration(ArchitectureConfiguration):
    qemu = "qemu-system-s390x"
    arch = "s390x"
    model = "s390-ccw-virtio"

    def __init__(self, kvm=True, uefi=False, model="s390-ccw-virtio") -> None:
        self.kvm = kvm
        self.uefi = uefi
        self.model = model

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
            cpu="<cpu mode='host-passthrough' check='none'/>" if self.kvm else "<cpu mode='custom' match='exact'><model>qemu</model></cpu>",
        )


def storage_device_name_generator():
    prefix = "vd"
    for i in range(26):
        yield prefix + string.ascii_lowercase[i]


storage_device_name = storage_device_name_generator()


class StorageDeviceConfiguration:
    path: str
    host_device_path: str

    def __init__(self) -> None:
        pass

    def generate(self) -> str:
        raise NotImplementedError()


class RawStorageDevice(StorageDeviceConfiguration):
    def __init__(self, path) -> None:
        self.path = path
        self.host_device_path = next(storage_device_name)

    def generate(self):
        return """
        <disk type='file' device='disk'>
            <driver name='qemu' type='raw'/>
            <source file="%s"/>
            <target dev='%s' bus='virtio'/>
        </disk>
        """ % (
            self.path,
            self.host_device_path,
        )


class QCow2StorageDevice(StorageDeviceConfiguration):
    def __init__(self, path, size=0, serial_str="") -> None:
        self.path = path
        self.size = size
        self.serial_str = serial_str
        self.host_device_path = next(storage_device_name)

    def generate(self):
        return """
        <disk type='file' device='disk'>
            <driver name='qemu' type='qcow2' cache='unsafe'/>
            <source file="%s"/>
            <target dev='%s' bus='virtio'/>
            <serial>%s</serial>
        </disk>
        """ % (
            self.path,
            self.host_device_path,
            self.serial_str,
        )


class NetworkConfiguration:
    mac_address: str
    additional_qemu_args: list[str]

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
        self.additional_qemu_args = [
            "-netdev",
            "user,id=testcloud_net.{},hostfwd=tcp::{}-:22,hostfwd=tcp::{}-:10022".format(port, port, (port - 1000)),
            "-device",
            "{},addr=1e.0,netdev=testcloud_net.{}".format(device_type, port),
        ]

    def generate(self):
        return """
        <interface type='user'>
            <mac address="{mac_address}"/>
            <model type='virtio'/>
        </interface>
        """.format(
            mac_address=self.mac_address,
        )


class TPMConfiguration:
    def __init__(self, version="2.0") -> None:
        super().__init__()
        self.version = version

    def generate(self):
        return """
        <tpm model='tpm-tis'>
            <backend type='emulator' version='{version}'/>
        </tpm>
        """.format(
            version=self.version
        )


class VIRTIOFSConfiguration:
    def __init__(self, source, target, count) -> None:
        super().__init__()
        self.source = source
        self.target = target
        self.count = count

    def generate(self):
        # Verify the source exists
        if not os.path.isdir(self.source):
            raise TestcloudInstanceError("Requested virtiofs mount: {source} doesn't exist.")
        return """
        <filesystem type="mount">
            <source dir="{source}"/>
            <target dir="{tag}"/>
            <driver type="virtiofs"/>
        </filesystem>
        """.format(
            source=self.source, tag="virtiofs-%d" % self.count
        )


class IOMMUConfiguration:
    def __init__(self, model="virtio") -> None:
        super().__init__()
        self.model = model

    def generate(self):
        return """
        <iommu model='{model}'/>
        """.format(
            model=self.model
        )


class DomainConfiguration:
    name: str
    cpu_count: int
    memory_size: int
    system_architecture: Optional[ArchitectureConfiguration]
    storage_devices: list[StorageDeviceConfiguration]
    network_configuration: Optional[NetworkConfiguration]
    tpm_configuration: Optional[TPMConfiguration]
    virtiofs_configuration: list[VIRTIOFSConfiguration]
    iommu_configuration: Optional[IOMMUConfiguration]
    qemu_args: list[str]
    qemu_envs: dict[str, str]
    coreos: Optional[bool]

    def __init__(self, name) -> None:
        config_data = config.get_config()
        self.uuid = uuid.uuid4()
        self.name = name
        self.path = "{}/instances/{}".format(config_data.DATA_DIR, self.name)
        self.local_disk = "{}/{}-local.qcow2".format(self.path, self.name)
        self.seed_path = "{}/{}-seed.img".format(self.path, self.name)
        self.xml_path = "{}/{}-domain.xml".format(self.path, self.name)
        self.config_path = "{}/{}.ign".format(self.path, self.name)  # CoreOS
        self.cpu_count = -1
        self.memory_size = -1
        self.system_architecture = None
        self.storage_devices = []
        self.network_configuration = None
        self.network_devices = []
        self.tpm_configuration = None
        self.virtiofs_configuration = []
        self.iommu_configuration = None
        self.qemu_args = []
        self.qemu_envs = {}
        self.coreos = False

    def generate_virtiofs_mounts(self) -> str:
        return "\n".join([virtiofs_mount.generate() for virtiofs_mount in self.virtiofs_configuration])

    def generate_virtiofs_head(self) -> str:
        return """
        <memoryBacking>
            <access mode="shared"/>
            <source type="memfd"/>
        </memoryBacking>
        """

    def generate_storage_devices(self) -> str:
        return "\n".join([device.generate() for device in self.storage_devices])

    def generate_network_devices(self) -> str:
        return "\n".join(
            [device.generate() for device in self.network_devices + ([self.network_configuration] if self.network_configuration else [])]
        )

    def get_emulator(self) -> str:
        assert self.system_architecture is not None
        qemu_paths = [
            # Try to query usable qemu binaries for desired architecture
            "/usr/bin/" + self.system_architecture.qemu,
            "/usr/libexec/" + self.system_architecture.qemu,
            # Some systems might only have qemu-kvm as the qemu binary, try that if everything else failed...
            "/usr/bin/qemu-kvm",
            "/usr/libexec/qemu-kvm",
        ]
        for path in qemu_paths:
            if os.path.exists(path):
                return path

        raise TestcloudInstanceError("No usable qemu binary exist, tried: %s" % qemu_paths)

    def get_qemu_args(self) -> str:
        assert self.network_devices is not [] or self.network_configuration is not None
        assert self.system_architecture is not None
        for network_device in self.network_devices + ([self.network_configuration] if self.network_configuration else []):
            self.qemu_args.extend(network_device.additional_qemu_args)
        if self.coreos:
            if type(self.system_architecture) in [AArch64ArchitectureConfiguration, X86_64ArchitectureConfiguration]:
                self.qemu_args.extend(["-fw_cfg", "name=opt/com.coreos/config,file=%s" % self.config_path])
            else:
                self.qemu_args.extend(
                    [
                        "-drive",
                        "file=%s,if=none,format=raw,readonly=on,id=ignition" % self.config_path,
                        "-device",
                        "virtio-blk,serial=ignition,drive=ignition,devno=fe.0.0008",
                    ]
                )
        return "\n".join(["<qemu:arg value='%s'/>" % qemu_arg for qemu_arg in self.qemu_args])

    def get_qemu_envs(self) -> str:
        return "\n".join(["<qemu:env name='%s' value='%s'/>" % (qemu_env, self.qemu_envs[qemu_env]) for qemu_env in self.qemu_envs])

    def generate(self) -> str:
        assert self.system_architecture is not None
        assert self.network_devices is not [] or self.network_configuration is not None

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
            {virtiofs_head}
            <devices>
                <emulator>{emulator_path}</emulator>
                {storage_devices}
                {network_configuraton}
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
                {virtiofs_device}
                {iommu}
            </devices>
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
            network_configuraton=self.generate_network_devices(),
            tpm=self.tpm_configuration.generate() if self.tpm_configuration else "",
            virtiofs_head=self.generate_virtiofs_head() if self.virtiofs_configuration else "",
            virtiofs_device=self.generate_virtiofs_mounts() if self.virtiofs_configuration else "",
            iommu=self.iommu_configuration.generate() if self.iommu_configuration else "",
            qemu_args=self.get_qemu_args(),
            qemu_envs=self.get_qemu_envs(),
        )
        almost_pretty_xml = xml.dom.minidom.parseString(domain_xml).toprettyxml(indent="  ")
        return os.linesep.join([s for s in almost_pretty_xml.splitlines() if s.strip()])


def _get_default_domain_conf(
    name: str,
    backingstore_image: image.Image,
    mac_address: Optional[str] = None,
    use_disk_serial: bool = False,
    disk_size: int = 0,
    disk_count: int = 1,
    nic_count: int = 1,
    tpm: bool = False,
    coreos: bool = False,
    connection: str = "qemu:///system",
    vcpus: Optional[int] = None,
    ram: Optional[int] = None,
    desired_arch: Optional[str] = None,
    virtiofs_source: Optional[str] = None,
    virtiofs_target: Optional[str] = None,
    iommu: bool = False,
):

    desired_arch = desired_arch or platform.machine()
    vcpus = vcpus or config_data.VCPUS
    ram = ram or config_data.RAM
    mac_address = mac_address or util.generate_mac_address()
    kvm = True if (desired_arch == platform.machine() and os.path.exists("/dev/kvm")) else False

    domain_configuration = DomainConfiguration(name)
    domain_configuration.cpu_count = vcpus
    domain_configuration.memory_size = ram * 1024

    if desired_arch == "x86_64":
        domain_configuration.system_architecture = X86_64ArchitectureConfiguration(
            kvm=kvm,
            uefi=config_data.UEFI,
            model="q35" if not util.needs_legacy_net(backingstore_image.name) else "pc")
    elif desired_arch == "aarch64":
        domain_configuration.system_architecture = AArch64ArchitectureConfiguration(kvm=kvm, uefi=True, model="virt")
    elif desired_arch == "ppc64le":
        domain_configuration.system_architecture = Ppc64leArchitectureConfiguration(kvm=kvm, uefi=False, model="pseries")
    elif desired_arch == "s390x":
        domain_configuration.system_architecture = S390xArchitectureConfiguration(kvm=kvm, uefi=False, model="s390-ccw-virtio")
    else:
        raise TestcloudInstanceError("Unsupported arch")

    if connection == "qemu:///system":
        domain_configuration.network_devices.append(SystemNetworkConfiguration(mac_address=mac_address))
        for i in range(nic_count - 1):
            mac_address = util.generate_mac_address()
            domain_configuration.network_devices.append(SystemNetworkConfiguration(mac_address=mac_address))

    elif connection == "qemu:///session":
        port = util.spawn_instance_port_file(name)
        device_type = "virtio-net-pci" if not util.needs_legacy_net(backingstore_image.name) else "e1000"
        domain_configuration.network_devices.append(UserNetworkConfiguration(mac_address=mac_address, port=port, device_type=device_type))
        for i in range(nic_count - 1):
            mac_address = util.generate_mac_address()
            domain_configuration.network_devices.append(
                UserNetworkConfiguration(mac_address=mac_address, port=port, device_type=device_type)
            )
    else:
        raise TestcloudInstanceError("Unsupported connection type")

    image = QCow2StorageDevice(domain_configuration.local_disk, disk_size, "")
    domain_configuration.storage_devices.append(image)

    if coreos:
        domain_configuration.coreos = True
        domain_configuration.qemu_args.extend(config_data.CMD_LINE_ARGS_COREOS)
        domain_configuration.qemu_envs.update(config_data.CMD_LINE_ENVS_COREOS)
    else:
        domain_configuration.qemu_args.extend(config_data.CMD_LINE_ARGS)
        domain_configuration.qemu_envs.update(config_data.CMD_LINE_ENVS)
        seed_disk = RawStorageDevice(domain_configuration.seed_path)
        domain_configuration.storage_devices.append(seed_disk)

    if tpm:
        domain_configuration.tpm_configuration = TPMConfiguration()

    for i in range(disk_count - 1):
        additional_disk_path = "{}/{}-local{}.qcow2".format(domain_configuration.path, name, i + 2)
        serial_str = "testcloud-{}".format(i + 1) if use_disk_serial else ""
        domain_configuration.storage_devices.append(QCow2StorageDevice(additional_disk_path, disk_size, serial_str))

    if virtiofs_source and virtiofs_target:
        domain_configuration.virtiofs_configuration.append(VIRTIOFSConfiguration(virtiofs_source, virtiofs_target, 0))

    if iommu:
        domain_configuration.iommu_configuration = IOMMUConfiguration()

    return domain_configuration
