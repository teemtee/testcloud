Name:           testcloud
# Update also version in testcloud/__init__.py and docs/source/conf.py when changing this!
Version:        0.9.10
Release:        1%{?dist}
Summary:        Tool for running cloud images locally

License:        GPL-2.0-or-later
URL:            https://pagure.io/testcloud
Source0:        https://releases.pagure.org/testcloud/%{name}-%{version}.tar.gz

ExclusiveArch: %{kernel_arches} noarch
BuildArch:      noarch

# Ensure we can create the testcloud group
Requires(pre):  shadow-utils

Requires:       polkit

Recommends:     edk2-ovmf

Requires:       python3-%{name} = %{version}-%{release}

%description
testcloud is a relatively simple system which is capable of booting images
designed for cloud systems on a local system with minimal configuration.
testcloud is designed to be (and remain) somewhat simple, trading fancy cloud
system features for ease of use and sanity in development.

%package -n python3-%{name}
Summary:        Python 3 interface to testcloud

Obsoletes:      python2-testcloud <= %{version}-%{release}

BuildRequires:  bash-completion
BuildRequires:  python3-libvirt
BuildRequires:  python3-devel
BuildRequires:  python3-jinja2
BuildRequires:  python3-pytest
BuildRequires:  python3-requests
BuildRequires:  python3-setuptools

Requires:       genisoimage
Requires:       libvirt-daemon-config-network
Requires:       libvirt-daemon-driver-qemu
Requires:       libvirt-daemon-driver-storage-core
Requires:       python3-requests
Requires:       python3-libvirt
Requires:       python3-jinja2
Recommends:     butane
Suggests:       python3-libguestfs
Suggests:       libguestfs-tools-c

%description -n python3-%{name}
Python 3 interface to testcloud.

# Create the testcloud group
%pre
getent group testcloud >/dev/null || groupadd testcloud

%prep
%autosetup -n %{name}-%{version} -p1
# Drop coverage testing
sed -i 's/ --cov-report=term-missing --cov testcloud//g' tox.ini

%build
%py3_build

%install
%py3_install

# Docs
install -d %{buildroot}%{_mandir}/man1
install -p -m 0644 manpages/testcloud.1 %{buildroot}%{_mandir}/man1

# configuration files
mkdir -p %{buildroot}%{_sysconfdir}/testcloud/
install conf/settings-example.py %{buildroot}%{_sysconfdir}/testcloud/settings.py

# Create running directory for testcloud
install -d %{buildroot}%{_sharedstatedir}/testcloud/

# Install domain jinja template for libvirt to import
install conf/domain-template.jinja %{buildroot}/%{_sharedstatedir}/testcloud/domain-template.jinja

# backingstores dir
install -d %{buildroot}/%{_sharedstatedir}/testcloud/backingstores

# instance dir
install -d %{buildroot}/%{_sharedstatedir}/testcloud/instances

# create polkit rules dir and install polkit rule
mkdir -p %{buildroot}%{_sysconfdir}/polkit-1/rules.d
install conf/99-testcloud-nonroot-libvirt-access.rules %{buildroot}%{_sysconfdir}/polkit-1/rules.d/99-testcloud-nonroot-libvirt-access.rules

# Copy bash completion script
mkdir -p %{buildroot}%{_datadir}/bash-completion/completions/
install conf/testcloud-bash %{buildroot}%{_datadir}/bash-completion/completions/testcloud

%check
%pytest
# Remove compiled .py files from /etc after os_install_post
rm -f %{buildroot}%{_sysconfdir}/testcloud/*.py{c,o}
rm -rf %{buildroot}%{_sysconfdir}/testcloud/__pycache__

%files
%doc README.md
%{_mandir}/man1/testcloud.1*
%license LICENSE

%dir %{_sysconfdir}/testcloud
%dir %attr(0775, qemu, testcloud) %{_sharedstatedir}/testcloud
%dir %attr(0775, qemu, testcloud) %{_sharedstatedir}/testcloud/backingstores
%dir %attr(0775, qemu, testcloud) %{_sharedstatedir}/testcloud/instances
%attr(0764, qemu, testcloud) %{_sharedstatedir}/testcloud/domain-template.jinja

%attr(0644, root, root) %{_sysconfdir}/polkit-1/rules.d/99-testcloud-nonroot-libvirt-access.rules

%config(noreplace) %{_sysconfdir}/testcloud/settings.py
%{_bindir}/testcloud
%{_bindir}/t7d
%{_datadir}/bash-completion/completions/testcloud

%files -n python3-%{name}
%{python3_sitelib}/testcloud
%{python3_sitelib}/*.egg-info

%changelog
* Mon Sep 04 2023 Fedora Release Engineering <releng@fedoraproject.org> - 0.9.10-1
- configuration abstraction (domain/apiv2 by lbrabec)
- Add workaround for Ubuntu
- Remove compatibility code for tmt < 1.22
- Drop long deprecated find_vm_ip from cli
- Always try to run dhclient in cloud-init
- Clarify that testcloud runs VMs and no containers (Anatoli Babenia)
- Support Fedora OpenStack images handling
- [Domain API] Cleanups, fixes, refactors, Part 1/n
- [Domain API] Cleanups, fixes, refactors, Part 2/n
- Downloader: support unknown file sizes, add retry mechanism
- domain/apiv2: Fix CoreOS
- Instance: inherit coreos param too for DomainConfiguration
- Storage: provide domain/apiv2 facilities for storage sizing, refactor

* Sat Jul 22 2023 Fedora Release Engineering <releng@fedoraproject.org> - 0.9.2-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_39_Mass_Rebuild

* Wed Jun 14 2023 Python Maint <python-maint@redhat.com> - 0.9.2-2
- Rebuilt for Python 3.12

* Wed Mar 22 2023 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.9.2-1
- Unbreak python <3.9

* Wed Mar 22 2023 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.9.1-1
- setup.py: Include distro_utils too
- inherit from Exception instead of BaseException
- get_image_url: return str of supported images instead of dict_keys in errors

* Sat Mar 18 2023 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.9.0-1
- image downloader: Try to detect failed downloads more aggressively
- CLI: Support download image
- CLI: Drop non-x86 warning
- CLI: Drop instance subcommand
- Rework images url handling
- CentOS 7: Bump image
- Vagrant: Support Fedora Boxes
- cli: Tune down default logging
- add disk_number param
- pc model: use q35
- memballoon: drop address spec
- Use unversioned machine models
- CentOS Stream: try to auto-detect the latest image
- support TPM2 device
- Prevent unbound url variable on failed Fedora rawhide/branched guess
- add mac_address param
- add qemu_cmds param for coreos testcases
- support to pass ignition file on platforms that doesn't support FW CFG
- Require libvirt-daemon-config-network as well

* Sat Jan 21 2023 Fedora Release Engineering <releng@fedoraproject.org> - 0.8.2-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_38_Mass_Rebuild

* Fri Dec 02 2022 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.8.2-1
- CentOS Stream {8,9}: bump image version
- Leave boot drive address guessing to libvirt
- Workaround libvirt/qemu PCI auto-assign issue

* Fri Sep 09 2022 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.8.1-3
- Require libvirt-daemon-config-network as well

* Sat Jul 23 2022 Fedora Release Engineering <releng@fedoraproject.org> - 0.8.1-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_37_Mass_Rebuild

* Thu Jun 30 2022 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.8.1-1
- CoreOS: Go on with COREOS_DATA replace failure

* Fri Jun 24 2022 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.8.0-1
- Bump CentOS Stream versions
- Build seed image with genisoimage (mpitt)
- Reduce libvirt dependencies (mpitt)
- Drop libguestfs from Requires to Suggests (mpitt)
- util: except also requests.exceptions.JSONDecodeError
- _needs_legacy_net: try to guess based on image name with missing guestfs
- add coreos aarch64 support (lnie)
- Allow to configure download progress verbosity

* Mon Jun 13 2022 Python Maint <python-maint@redhat.com> - 0.7.1-2
- Rebuilt for Python 3.11

* Thu May 05 2022 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.7.1-1
- Try qemu-kvm if there is nothing else...

* Mon May 02 2022 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.7.0-1
- non-x86 support
- cli: Fixup crash on vm start in connection tip
- Handle missing testcloud group also while creating instances from local image

* Thu Jan 27 2022 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.6.4-1
- fix selinux detection for image context (olichtne)
- Drop dependency on python-mock
- Drop coverage testing in rpm build

* Sat Jan 22 2022 Fedora Release Engineering <releng@fedoraproject.org> - 0.6.3-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_36_Mass_Rebuild

* Wed Dec 01 2021 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.6.3-1
- Drop Atomic Host
- Simplify cli codepath, use cloud-user by default
- cli: allow to spearate OS version by "-"
- CentOS misc: improve error output on missing version
- Disable UseDNS, GSSAPI for faster SSH, allow ssh for root
- CentOS: Fix el7 based systems
- CentOS: update 7 build, add CentOS Stream 9

* Mon Sep 27 2021 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.6.2-1
- Workaround EL8 bug - waiting for sshd restart with user sessions
- Add a basic integration test and plan for tmt
- Fixes around backingstore cleanups
- get_fedora_image_url: Proper support for branched, cleanups
- get_fedora_image_url: Add info when user asks for wrong version
- Don't use hammer solution to all Vagrant boxes, force-install cloud-init to known broken images
- non-x86_64 support preparations and downloader code
- Don't rely on working qemu://system

* Fri Jul 23 2021 Fedora Release Engineering <releng@fedoraproject.org> - 0.6.1-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_35_Mass_Rebuild

* Wed Jul 21 2021 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.6.1-1
- Add wait and retry around dom.create()
- lazy_refcounts=on and cache=unsafe
- Bash completion (by lbrabec)
- Let's have also short t7d binary
- Add long project description for pypi
- Style: Let's not have lines with hundreds of characters...
- API: Add reboot function
- FileLock: Make sure we don't overwrite config_data.DATA_DIR
- Fix systems using systemd-networkd in user session mode

* Fri Jul 09 2021 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.6.0-1
- SPEC: Use pytest macro
- Merge downstream spec changes
- README: Let's believe in testcloud a bit more 😎
- Simplify cli warning wording a bit
- Remove forced reboot from cli for CentOS user sessions
- API: Allow to specify pci network device
- README: improve a tiny bit
- Make url mandatory, cleanup cli instance create a bit
- Allow to specify number of CPU cores to be assigned
- Change cli layout for instance create a bit (A LOT 😱 )
- get_debian_image_url: return None on fail
- Add a way to shutdown vms in a graceful way
- use if hasattr insteadd of try/except AttributeError
- Use virtio-net-pci instead of e1000 for hostfwd in qemu user sessions
- implement synchronization using file lock for user sessions
- Don't directly alter config_object, use a copy of it
- Fixup CentOS short handle
- Support Ubuntu and Debian images
- Update url for oraculum
- Bunch of code shuffling
- Bunch of improvements for get_fedora_image_url
- Fixup traceback for unknown distributions on un-defined variable
- Fixups around system x session instances handling
- Dont blow out traceback on image download 404, fixup connection tooltip for CentOS
- Support fetching the latest Fedora Rawhide iso as fedora:rawhide url
- Support CentOS and CentOS Stream versions (hardcoded urls)
- Support operating with Vagrant images
- check whether the instance existing before do the prepare work
- Make the code more robust
- Make list and clean functions more robust to handle both system and user sessions
- add coreos test function

* Fri Jun 04 2021 Python Maint <python-maint@redhat.com> - 0.5.0-2
- Rebuilt for Python 3.10

* Mon Mar 22 2021 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.5.0-1
- Fix crash in _handle_connection_tip
- Allow to create an instance without specifying a name
- Fix instance.image_path
- Make network working in qemu:///session

* Wed Dec 16 2020 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.4.0-1
- Support creating instances by fedora:XX, fedora:latest and fedora:qa-matrix strings
- Implement auto cleaning of backingstore
- Make testcloud compatible with future Python 3.10
- Adapt to requests defaulting to simplejson if present
- Don't throw out exception when trying to create instance already existing in libvirt
- --all is now the default in testcloud instance list
- Show some hints to the users on instance create/start
- cleanup the instance bits when instance create fails

* Mon Nov 16 2020 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.3.7-1
- Do not throw out ugly tracebacks if user uses cli (#1887815)
- Parse CMD_LINE_ARGS and add CMD_LINE_ENVS (https://pagure.io/testcloud/issue/49)
- Add try/except check to instance.prepare() as permissions error can occur there too
- Update documentation
- Add manpage

* Fri Oct 09 2020 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.3.6-1
- Improve user experience when testcloud fails because of missing group

* Thu Aug 27 2020 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.3.5-4
- ExclusiveArch to prevent koji from trying to build this on i686

* Wed Jul 29 2020 Fedora Release Engineering <releng@fedoraproject.org> - 0.3.5-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_33_Mass_Rebuild

* Tue May 26 2020 Miro Hrončok <mhroncok@redhat.com> - 0.3.5-2
- Rebuilt for Python 3.9

* Fri May 22 2020 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.3.5-1
- Typo fix in RHEL 8 qemu-kvm naming workaround

* Thu May 21 2020 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.3.4-1
- Ugly hotfix for tmt

* Wed May 20 2020 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.3.3-1
- Support RHEL 8 hosts (different qemu-kvm path)
- Move most of the deps into python3-testcloud

* Sun Apr 19 2020 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.3.2-1
- Require only libguestfs-tools-c from libguestfs
- Bump default RAM size to 768 MB
- Fix for libvirt >= 6.0
- Fix DeprecationWarning: invalid escape sequence \w

* Mon Mar 02 2020 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.3.1-1
- Remove Python 2 support
- Raise TestcloudImageError if failed to open file
- instance: call qemu-img in quiet mode

* Fri Jan 31 2020 Fedora Release Engineering <releng@fedoraproject.org> - 0.3.0-5
- Rebuilt for https://fedoraproject.org/wiki/Fedora_32_Mass_Rebuild

* Thu Oct 03 2019 Miro Hrončok <mhroncok@redhat.com> - 0.3.0-4
- Rebuilt for Python 3.8.0rc1 (#1748018)

* Mon Aug 19 2019 Miro Hrončok <mhroncok@redhat.com> - 0.3.0-3
- Rebuilt for Python 3.8

* Sat Jul 27 2019 Fedora Release Engineering <releng@fedoraproject.org> - 0.3.0-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_31_Mass_Rebuild

* Wed May 22 2019 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.3.0-1
- Support creating UEFI VMs

* Sun Feb 03 2019 Fedora Release Engineering <releng@fedoraproject.org> - 0.2.2-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_30_Mass_Rebuild

* Tue Nov 20 2018 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.2.2-1
- drop and obsolete python2-testcloud on Fedora >= 30
- Fix setup.py test to also work with Python 3 (pytest-3)

* Sat Jul 14 2018 Fedora Release Engineering <releng@fedoraproject.org> - 0.2.1-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_29_Mass_Rebuild

* Mon Jul 02 2018 Miro Hrončok <mhroncok@redhat.com> - 0.2.1-2
- Rebuilt for Python 3.7

* Fri Jun 29 2018 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.2.1-1
- domain-template: use cpu host-passthrough
- domain-template: use urandom for RNG

* Tue Jun 19 2018 Miro Hrončok <mhroncok@redhat.com> - 0.2.0-2
- Rebuilt for Python 3.7

* Wed May 30 2018 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.2.0-1
- Drop Fedora 26
- Use Python 3 by default
- Remove shebangs from non-executables
- Split testcloud into testcloud, python2-testcloud and python3-testcloud

* Wed May 02 2018 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.1.18-1
- Host /dev/random passthrough

* Tue Mar 06 2018 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.1.17-1
- Add instance clean command
- Ignore error when domain stopped between stop attempts
- Add Makefile

* Tue Feb 20 2018 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.1.16-1
- Retry to stop instance when host is busy

* Fri Feb 09 2018 Fedora Release Engineering <releng@fedoraproject.org> - 0.1.15-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_28_Mass_Rebuild

* Fri Feb 02 2018 Frantisek Zatloukal <fzatlouk@redhat.com> - 0.1.15-2
- Update Python 2 dependency declarations to new packaging standards
  (See https://fedoraproject.org/wiki/FinalizingFedoraSwitchtoPython3)

* Thu Oct 26 2017 Kamil Páral <kparal@redhat.com> - 0.1.15-1
- keep backwards compatible API

* Thu Oct 26 2017 Kamil Páral <kparal@redhat.com> - 0.1.14-1
- replace arp with libvirt method (lose dep on net-tools)
- fix test suite in spec file

* Thu Jul 27 2017 Fedora Release Engineering <releng@fedoraproject.org> - 0.1.11-4
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Mass_Rebuild

* Wed Feb 22 2017 Kamil Páral <kparal@redhat.com> - 0.1.11-3
- don't install py[co] files into /etc

* Mon Feb 20 2017 Kamil Páral <kparal@redhat.com> - 0.1.11-2
- add python-pytest-cov builddep to run test suite during building

* Mon Feb 20 2017 Kamil Páral <kparal@redhat.com> - 0.1.11-1
- make libvirt url configurable
- avoid race condition during listing domains

* Sat Feb 11 2017 Fedora Release Engineering <releng@fedoraproject.org> - 0.1.10-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_26_Mass_Rebuild

* Wed Aug 17 2016 Martin Krizek <mkrizek@redhat.com> - 0.1.10-1
- use symlinks for file:// urls
- look for the jinja template in the conf/ dir first

* Tue Jul 19 2016 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 0.1.9-2
- https://fedoraproject.org/wiki/Changes/Automatic_Provides_for_Python_RPM_Packages

* Tue Jul 19 2016 Kamil Páral <kparal@redhat.com> - 0.1.9-1
- upstream 0.1.9 release
- "destroy" commands renamed to "remove"
- "instance remove" now supports "--force"
- new "instance reboot" command
- no more crashes when stopping an already stopped instance
- option to automatically stop an instance during remove (API)

* Mon Jul 18 2016 Martin Krizek <mkrizek@redhat.com> - 0.1.8-3
- libguestfs on arm should be fixed now, removing exclude arm

* Wed Jun 22 2016 Martin Krizek <mkrizek@redhat.com> - 0.1.8-2
- exclude arm until libguestfs dep is resolved there

* Fri Feb 05 2016 Tim Flink <tflink@fedoraproject.org> - 0.1.8-1
- Explicitly fail when IP address is not found

* Fri Feb 05 2016 Fedora Release Engineering <releng@fedoraproject.org> - 0.1.7-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_24_Mass_Rebuild

* Tue Dec 8 2015 Tim Flink <tflink@fedoraproject.org> - 0.1.7-1
- Enabling configurable instance memory and disk size (T420, T659)
- Improved handling of images with larger disks (T657)
- Changed "cache" to "backingstores" to reduce confusion (T521)

* Tue Dec 1 2015 Tim Flink <tflink@fedoraproject.org> - 0.1.6-1
- fixing python2 macros
- other small fixes as per review

* Wed Nov 18 2015 Tim Flink <tflink@fedoraproject.org> - 0.1.5-4
- adding net-tools as a dependency

* Wed Nov 11 2015 Martin Krizek <mkrizek@redhat.com> - 0.1.5-3
- adding python-jinja2 as a dependency

* Thu Nov 05 2015 Tim Flink <tflink@fedoraproject.org> - 0.1.5-2
- rework setup to work with github sources, proper file declarations

* Wed Nov 04 2015 Mike Ruckman <roshi@fedoraproject.org> - 0.1.5-1
- Multiple bugfixes (mainly use libvirt, not virt-install)

* Tue Sep 29 2015 Mike Ruckman <roshi@fedoraproject.org> - 0.1.4-2
- Fix permissions issues and no long overwrite stored configs.

* Tue Sep 29 2015 Mike Ruckman <roshi@fedoraproject.org> - 0.1.4-1
- Multiple bug fixes.

* Tue Sep 01 2015 Mike Ruckman <roshi@fedoraproject.org> - 0.1.3-2
- Unkludge the last release.

* Sun Aug 30 2015 Mike Ruckman <roshi@fedoraproject.org> - 0.1.3-1
- Multiple bugfixes and general clean up.

* Tue Jul 14 2015 Mike Ruckman <roshi@fedoraproject.org> - 0.1.1-2
- Added polkit rule for headless machine (or passwordless) execution.

* Thu Jul 09 2015 Mike Ruckman <roshi@fedoraproject.org> - 0.1.1-1
- Fixed packaging issues. Removed uneeded code.

* Thu Jul 09 2015 Mike Ruckman <roshi@fedoraproject.org> - 0.1.0-2
- Fixed packaging issues. Removed uneeded code.

* Tue Jun 23 2015 Mike Ruckman <roshi@fedoraproject.org> - 0.1.0-1
- Initial packaging of testcloud
