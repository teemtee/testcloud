%if 0%{?rhel} <= 9
%global _sysusersdir /usr/lib/sysusers.d
%endif

Name:           testcloud
Version:        0.0.0
Release:        %autorelease
Summary:        Tool for running cloud images locally

License:        GPL-2.0-or-later
URL:            https://github.com/teemtee/testcloud
Source0:        %{pypi_source testcloud}
Source1:        testcloud.sysusers

ExclusiveArch: %{kernel_arches} noarch
BuildArch:      noarch

BuildRequires:  systemd-rpm-macros
%{?sysusers_requires_compat}

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

BuildRequires:  bash-completion
BuildRequires:  python3-devel
BuildRequires:  python3-pytest

Requires:       acl
Requires:       genisoimage
Requires:       libvirt-daemon
Requires:       libvirt-daemon-config-network
Requires:       libvirt-daemon-driver-qemu
Requires:       libvirt-daemon-driver-storage-core
Recommends:     butane
Suggests:       python3-libguestfs
Suggests:       libguestfs-tools-c

%description -n python3-%{name}
Python 3 interface to testcloud.

%pre
%sysusers_create_compat %{SOURCE1}

%prep
%autosetup -n %{name}-%{version} -p1
# Drop coverage testing
sed -i 's/ --cov-report=term-missing --cov testcloud//g' tox.ini

%generate_buildrequires
%pyproject_buildrequires

%build
export SETUPTOOLS_SCM_PRETEND_VERSION=%{version}
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files testcloud

# man page
mkdir -p %{buildroot}%{_mandir}/man1
install -pm 644 manpages/testcloud.1 %{buildroot}%{_mandir}/man1

# bash completion
mkdir -p %{buildroot}%{_datadir}/bash-completion/completions
install -pm 644 conf/testcloud %{buildroot}%{_datadir}/bash-completion/completions/testcloud

# configuration files
mkdir -p %{buildroot}%{_sysconfdir}/testcloud/
install conf/settings-example.py %{buildroot}%{_sysconfdir}/testcloud/settings.py

# Create running directory for testcloud
install -d %{buildroot}%{_sharedstatedir}/testcloud/

# backingstores dir
install -d %{buildroot}/%{_sharedstatedir}/testcloud/backingstores

# instance dir
install -d %{buildroot}/%{_sharedstatedir}/testcloud/instances

# create polkit rules dir and install polkit rule
mkdir -p %{buildroot}%{_sysconfdir}/polkit-1/rules.d
install conf/99-testcloud-nonroot-libvirt-access.rules %{buildroot}%{_sysconfdir}/polkit-1/rules.d/99-testcloud-nonroot-libvirt-access.rules

# sysusers conf file for creation of testcloud group
install -p -m644 -D %{SOURCE1} %{buildroot}%{_sysusersdir}/%{name}.conf

%check
%pyproject_check_import
%pytest

%files
%doc README.md
%{_mandir}/man1/testcloud.1*
%license LICENSE

%dir %{_sysconfdir}/testcloud
%dir %attr(0775, qemu, testcloud) %{_sharedstatedir}/testcloud
%dir %attr(0775, qemu, testcloud) %{_sharedstatedir}/testcloud/backingstores
%dir %attr(0775, qemu, testcloud) %{_sharedstatedir}/testcloud/instances

%attr(0644, root, root) %{_sysconfdir}/polkit-1/rules.d/99-testcloud-nonroot-libvirt-access.rules

%config(noreplace) %{_sysconfdir}/testcloud/settings.py
%{_bindir}/testcloud
%{_bindir}/t7d
%{_datadir}/bash-completion/completions/testcloud

%{_sysusersdir}/%{name}.conf

%files -n python3-%{name} -f %{pyproject_files}

%changelog
%autochangelog
