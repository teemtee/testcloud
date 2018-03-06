# sitelib for noarch packages, sitearch for others (remove the unneeded one)
%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}

Name:           testcloud
Version:        0.1.17
Release:        1%{?dist}
Summary:        Tool for running cloud images locally

License:        GPLv2+
URL:            https://pagure.io/testcloud
Source0:        https://releases.pagure.org/testcloud/%{name}-%{version}.tar.gz

BuildArch:      noarch

# Ensure we can create the testcloud group
Requires(pre):  shadow-utils

# testcloud integrates with libvirt
Requires:       libvirt
%if 0%{?fedora} <= 26
Requires:       libvirt-python
%else
Requires:       python2-libvirt
%endif

# This is used to manipulate images on disk
Requires:       libguestfs
Requires:       libguestfs-tools

# Used to download images from valid URLs
Requires:       python2-requests

Requires:       polkit
Requires:       python2-jinja2

%if 0%{?fedora} <= 26
BuildRequires:  libvirt-python
%else
BuildRequires:  python2-libvirt
%endif
BuildRequires:  python2-devel
BuildRequires:  python2-jinja2
BuildRequires:  python2-mock
BuildRequires:  python2-pytest
BuildRequires:  python2-pytest-cov
BuildRequires:  python2-requests
BuildRequires:  python2-setuptools

# Provides:       python2-testcloud

%description
testcloud is a relatively simple system which is capable of booting images
designed for cloud systems on a local system with minimal configuration.
testcloud is designed to be (and remain) somewhat simple, trading fancy cloud
system features for ease of use and sanity in development.

# Create the testcloud group
%pre
getent group testcloud >/dev/null || groupadd testcloud

%prep
%setup -q -n %{name}-%{version}

%check
%{__python2} setup.py test
# Remove compiled .py files from /etc after running unittests
rm -f %{buildroot}%{_sysconfdir}/testcloud/*.py{c,o}

%build
%{__python2} setup.py build

%install
%{__python2} setup.py install -O1 --skip-build --root %{buildroot}

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

%files
%doc README.rst
%license LICENSE
%{python2_sitelib}/testcloud
%{python2_sitelib}/*.egg-info

%dir %{_sysconfdir}/testcloud
%dir %attr(0775, qemu, testcloud) %{_sharedstatedir}/testcloud
%dir %attr(0775, qemu, testcloud) %{_sharedstatedir}/testcloud/backingstores
%dir %attr(0775, qemu, testcloud) %{_sharedstatedir}/testcloud/instances
%attr(0764, qemu, testcloud) %{_sharedstatedir}/testcloud/domain-template.jinja

%attr(0644, root, root) %{_sysconfdir}/polkit-1/rules.d/99-testcloud-nonroot-libvirt-access.rules

%config(noreplace) %{_sysconfdir}/testcloud/settings.py
%{_bindir}/testcloud

%changelog
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
