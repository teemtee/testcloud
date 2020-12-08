.. testcloud documentation master file, created by
   sphinx-quickstart on Wed May 20 14:59:21 2015.

.. Last updated on Fri Nov 13 13:56:10 2020.

.. This work is licensed under the Creative Commons Attribution 4.0
   International License. To view a copy of this license, visit
   http://creativecommons.org/licenses/by/4.0/.

======================
Testcloud User's Guide
======================

**testcloud** is a simple system which is capable of downloading images designed
for cloud systems and booting them locally with minimial configuration needed.
**testcloud** is designed to be simple and lean, trading fancy cloud
system features for ease of use and sanity in development.

At this time, only *Fedora qcow2* images are supported. This might change in the
future.


Installation
============

To install **testcloud** on a production system:

    #. Install the testcloud package.

        .. code-block:: bash

            $ sudo dnf install testcloud

    #. Add yourself to the testcloud group.

        .. code-block:: bash

            $ sudo usermod -a -G testcloud $USER

    #. Restart your user session to update the group privileges, or use ``su -`` to get a login shell for that particular user where the group settings will be updated.

        .. code-block:: bash

            $ su -i $USER

    Now, you are ready to use testcloud.

For development purposes, see the :ref:`development` section below.

Using testcloud
===============

Creating a new instance
-----------------------

To create a new instance, **testcloud** must be given an image location URL from where it will download the image to create the instance. Currently, the image must be a *qcow2* image. If you do not have an image location of your own, you can use one of the images from the `Fedora Cloud download pages <https://alt.fedoraproject.org/cloud/>`_.

To create a new instance with the cloud image:

.. code-block:: bash

    $ testcloud instance create <instance name> -u <qcow2-image-url>

**testcloud** will download the qcow2 image and save it in the ``/var/lib/testcloud/backingstores/<qcow2-filename>``. It will use this image a backing store for the newly created instance in ``/var/tmp/instances/<instance-name>``. When the image has been already downloaded, **testcloud** will use the previously download image to create the instance instead.

Available options to create an instance
---------------------------------------

There are several options (most of them optional) that can be used to create a new instance using **testcloud**.

--ram RAM

    To set the amount of RAM that will be available to the virtual machine (in MiB).
--no-graphic

    This turns off the graphical display of the virtual machine.
--vnc

    To open a VNC connection at the :1 display of the instance.
-u, --url URL

    The URL from where the qcow2 image should be downloaded. This option is **compulsory**.
--timeout TIMEOUT

    A time (in seconds) to wait for boot to complete. Setting to 0 (default) will disable this functionality.
--disksize DISKSIZE

    To set the disk size of the virtual machine (in GiB)


Working with instances
----------------------

Instances can be manipulated using the ``instance`` command and specifying a single operation with a subcommand.

    #. To list running instances:

        .. code-block:: bash

            $ testcloud instance list

    #. To start the instance:

        .. code-block:: bash

            $ testcloud instance start <instance-name>

    #. To stop the instance:

        .. code-block:: bash

            $ testcloud instance stop <instance-name>

    #. To remove a stopped instance:

        .. code-block:: bash

            $ testcloud instance remove <instance-name>

    #. To remove a running instance:

        .. code-block:: bash

            $ testcloud instance remove -f <instance-name>

    #. To reboot the instance:

        .. code-block:: bash

            $ testcloud instance reboot <instance-name>

    #. To remove non-existing libvirt VMs from testcloud:

        .. code-block:: bash

            $ testcloud instance clean

Alternatively, the instances can also be viewed and manipulated using the **virt-manager** tool.

Logging into the instance
-------------------------

When the instance is created, **testcloud** will return its IP address that you can use to access the running instance via **ssh**. The login name is ``fedora`` and the password is ``passw0rd``.

To log onto the instance:

.. code-block:: bash

    $ ssh fedora@<instance-IP>

The IP address of an instance is also shown when you list the instance using the **testcloud** instance list command. You can also control the instance using the **virt-manager** tool.

Configuration
-------------

The default configuration should work for many people but those defaults can be overridden through the use of a ``settings.py`` file containing the values to use when overriding default settings. The example file in ``conf/settings-example.py`` shows the possible configuration values which can be changed.

Note that in order for those new values to be picked up, the filename cannot differ from ``settings.py`` and that file must be placed in one of the following locations:

* ``conf/settings.py`` in the git checkout
* ``~/.config/testcloud/settings.py``
* ``/etc/testcloud/settings.py``

For example, if you wanted to set up an **ssh** accessible root account that uses an *ssh key* as the authentification method, you could provide the following to the ``~/.config/testcloud/settings.py``:

.. code-block:: python

    USER_DATA = """#cloud-config
    users:
        - default
        - name: root
              password: %s
              chpasswd: { expire: False }
              ssh-authorized-keys:
        - <my ssh pub key>
    """

Getting Help
============

Self service methods for asking questions and filing tickets:

 * `Source Repository <https://pagure.io/testcloud>`_

 * `Currently Open Issues <https://pagure.io/testcloud/issues>`_

For other questions, the best places to ask are:

 * `The #fedora-qa IRC channel on Freenode <http://webchat.freenode.net/?channels=#fedora-qa>`_

 * `The qa-devel mailing list <https://admin.fedoraproject.org/mailman/listinfo/qa-devel>`_

Licenses
========

The **testcloud** library is licensed as `GNU General Public Licence v2.0 or later
<http://spdx.org/licenses/GPL-2.0+>`_.

The documentation for **testcloud** is licensed under a `Creative Commons
Atribution-ShareAlike 4.0 International License <https://creativecommons.org/licenses/by-sa/4.0/>`_.


Further reading
===============

.. toctree::
   :maxdepth: 2

   indepth
   develop
   api

==================
Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


