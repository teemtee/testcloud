# testcloud

**testcloud** is a small helper script to download and boot cloud/coreos images
locally. Testcloud supports wide range of distributions, namely Fedora, Fedora CoreOS,
CentOS, CentOS Stream, Red Hat Enterprise Linux, Debian and Ubuntu.

**testcloud** can run either in system mode or in constrained user session mode,
which is usefull for running it eg. in unprivileged containers.

## Installation

The following procedure should only be used to install **testcloud** on
a production system. For developing purposes, you need a different kind
of installation which is described in the **Testcloud Development**
section below.

To use **testcloud** on a production system:

1. Install the **testcloud**.

       ```
       $ sudo dnf install testcloud
       ```

2. Add yourself to the `testcloud group`.

      ```
      $ sudo usermod -a -G testcloud $USER
      ```

3. Restart your user session to update the group privileges, or use
   `su -` to get a login shell for that particular user where the group
   settings will be updated.

      ```
      $ su -i $USER
      ```

4. Now, you are ready to use **testcloud**.

## Using testcloud

### Creating a new instance

To create a new instance, you will need to provide distribution and version you wish to use or the url of some cloud
image in the *qcow2* format. If you do not have an image location of
your own, you can use the image from the **Fedora Cloud** download pages
(<https://alt.fedoraproject.org/cloud/>).

To create a new instance with the cloud image, run:

```
$ testcloud instance create <url for qcow2 image> or <distro:version>
```

Some examples how to create an instance with distribution:version shortcut:

```
# Latest Fedora Release
$ testcloud instance create fedora:latest
```

or, you can skip latest, which is the default value for version:
```
# Latest Fedora Release
$ testcloud instance create fedora
```

```
# Fedora Rawhide (latest Nightly Compose)
$ testcloud instance create fedora:rawhide
```

```
# CentOS Stream 8
$ testcloud instance create centos-stream:8
```

```
# Ubuntu Hirsute (21.04)
$ testcloud instance create ubuntu:hirsute
```

```
# Debian 11
$ testcloud instance create debian:11
```

Supported distributions with shortcuts are: Fedora, CentOS, CentOS Stream, Ubuntu and Debian. For other distributions, you can provide link to basically any qcow2 image which has the cloud-init package included.

Testcloud supports also Vagrant .box files, in a limited manner and currently only for CentOS.

**testcloud** will download the *qcow2* image and save it in the
`/var/lib/testcloud/backingstores/<qcow2-filename>`. It will use this
image a backing store for the newly created instance in
`/var/tmp/instances/<instance-name>`. When the image has been already
downloaded, **testcloud** will use the previously download image to
create the instance.

To create a new instance with the coreos image, run:

```
$ testcloud instance create fedora-coreos:<stream> --ssh_path < path of ssh pub key>

or

$ testcloud instance create fedora-coreos:<stream> --fcc_file < path of fcc file>

or

$ testcloud instance create fedora-coreos:<stream> --ign_file < path of ign file>
```
Only --ssh_path/--fcc_file/--ign_file is required

You will be able to see the instance using the `list` command.

```
$ testcloud instance list
```

Alternatively, the instances can also be viewed and manipulated using
the **virt-manager** tool.

### Starting, stopping, and removing an instance

Instances can be started and stopped using the `instance` interface of
the **testcloud**, too:

1. List all instances to see the correct name of the instance:

       ```
       $ testcloud instance list
       ```

2. Start the instance:

       ```
       $ testcloud instance start <instance-name>
       ```

3. Stop the instance:

       ```
       $ testcloud instance stop <instance-name>
       ```

4. Remove the instance:

       ```
       $ testcloud instance remove <instance-name>
       ```

Removing the instance only succeeds when the appropriate instance has
been **stopped** before. However, you can use the `-f` option to force
removing the instance.

### Other instance operations

1. Reboot the instance:

       ```
       $ testcloud instance reboot <instance-name>
       ```

2. Remove non-existing libvirt VMs from testcloud:

       ```
       $ testcloud instance clean
       ```

### Logging into the instance

When the cloud instance is created, **testcloud** will return its IP address
that you can use to access the running instance via `ssh`. The default *login
name* is `fedora` and the *password* is `passw0rd` for Fedora instances. Testcloud will output info how you can connect to any of the Supported Distributions.

```
ssh fedora@<instance-IP>
```
When the coreos instance is created, **testcloud** will return its IP address
that you can use to access the running instance via `ssh`. The *login
name* is `coreos`.

```
ssh coreos@<instance-IP>
```

The IP address of an instance is also shown when you list the instance
using the `testcloud instance list` command. You can also control the
instance using the **virt-manager** , **GNOME Boxes** or any other tool to manage libvirt VMs.

### Available options to create an instance

There are several options (all optional) that can be used to create a
new instance using **testcloud**.

-c, \--connection QEMU_URI

: You can specify uri to qemu you wish to use. For limited environments, you might wish to use *qemu:///session*. Remote connections other than *qemu:///session* and *qemu:///system* (like qemu+ssh,...) are known to be problematic.

\--ram RAM

: To set the amount of RAM that will be available to the virtual
    machine (in MiB).

\--vcpus VCPUS

: To set the amount of VCPUS that will be available to the virtual
    machine.

\--no-graphic

: This turns off the graphical display of the virtual machine.

\--vnc

: To open a VNC connection at the `:1` display of the instance.

-n, \--name NAME

: To specify a custom name for you instance.

\--timeout TIMEOUT

: A time (in seconds) to wait for boot to complete. Setting to 0
    (default) will disable this functionality.

\--disksize DISKSIZE

: To set the disk size of the virtual machine (in GiB)

There are several additional options that can be used to create a
new Coreos instance using **testcloud**.

\--fcc_file FCC_FILE

: To provide a fcc_file you want to use

\--ign_file IGN_FILE

: To provide an ign_file you want to use

\--ssh_path

: To provide ssh pubkey path

Please note --ssh_path ,--ign_file or --fcc_file  must be passed for Fedora CoreOS instances.

### Configuration

The default configuration should work for many people but those defaults
can be overridden through the use of a `settings.py` file containing the
values to use when overriding default settings. The example file in
`conf/settings-example.py` shows the possible configuration values which
can be changed.

Note that in order for those new values to be picked up, the filename
must be `settings.py` and that file must live in one of the following
locations:

* `conf/settings.py` in the git checkout
* `~/.config/testcloud/settings.py`
* `/etc/testcloud/settings.py`

For example, if you wanted to set up an ssh accessible root account that
uses an ssh key as the authentification method, you could provide the
following to the `~/.config/testcloud/settings.py`:

```yaml
USER_DATA = """#cloud-config
users:
    - default
    - name: root
      password: %s
      chpasswd: { expire: False }
      ssh-authorized-keys:
      - <my ssh pub key>
"""
```

## Testcloud Development

To develop **testcloud**, you need to perform a more complicated process
to install all its dependencies, download the source code and perform a
set-up.

To install **testcloud** for development purposes:

### Prerequisites

1. Install the dependencies for **testcloud**.

       ```
       $ sudo dnf install libvirt python3-libvirt libguestfs libguestfs-tools python3-requests python3-jinja2
       ```

2. Start **libvirtd**.

       ```
       $ sudo systemctl start libvirtd
       ```

3. Add the `testcloud` group to the system.

       ```
       $ sudo groupadd testcloud
       ```

4. Add a user into the `testcloud` group.

       ```
       $ sudo usermod -a -G testcloud $USER
       ```

5. Log out of the system and log in again to update the group
   information on your user or use a login shell on a different
   terminal.

       ```
       $ su - $USER
       ```

### Installation

1. Clone the **testcloud** repository.

       ```
       $ git clone https://pagure.io/testcloud.git
       ```

2. Create the application directories.

       ```
       $ sudo mkdir -p -m 775 /var/lib/testcloud
       ```

       ```
       $ sudo mkdir -p -m 775 /var/lib/testcloud/instances
       ```

       ```
       $ sudo mkdir -p -m 775 /var/lib/testcloud/backingstores
       ```

3. Change ownership on these directories to enable their use with
   **testcloud**.

       ```
       $ sudo chown qemu:testcloud /var/lib/testcloud
       ```

       ```
       $ sudo chown qemu:testcloud /var/lib/testcloud/instances
       ```

       ```
       $ sudo chown qemu:testcloud /var/lib/testcloud/backingstores
       ```

4. Copy the `.rules` file to the **polkit** rules.

       ```
       $ sudo cp conf/99-testcloud-nonroot-libvirt-access.rules /etc/polkit-1/rules.d/
       ```

### Running testcloud

1. Navigate to your **testcloud** git repository.

       ```
       $ cd testcloud
       ```

2. Execute the `run_testcloud.py` script to run the **testcloud**. You
   can use any options as with the regular installation, for example:

       ```
           $ ./run_testcloud.py instance create ...
       ```

3. Alternatively, you can use **pip** to install **testcloud** onto the
   system and then use it like it has been installed normally.

       ```
       $ pip3 install -e . --user
       ```

### Testing

There is a small testsuite you can run with:

```
tox
```

This is a good place to contribute if you\'re looking to help out.

### Issue Tracking and Roadmap

Our project tracker is on the Fedora QA-devel
[Pagure](https://pagure.io/testcloud//) instance.

### Credit

Thanks to [Oddshocks](https://github.com/oddshocks) for the koji
downloader code :)

### License

This code is licensed GPLv2+. See the LICENSE file for details.
