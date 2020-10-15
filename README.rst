testcloud
##########

**testcloud** is a small helper script to download and boot cloud images locally.
Currently, only Fedora *qcow2* images are tested and supported.

Installation
============

#. Install the **testcloud**:

    .. code:: bash

        sudo dnf install testcloud

#. Add yourself to the ``testcloud group``:

    .. code:: bash

        sudo usermod -a -G testcloud <username>

#. Restart your user session to update the group privileges, or use ``su -`` to get a login shell for that particular user where the group settings will be updated.

    .. code:: bash

        su -i <username>

#. Now, you are ready to use **testcloud**.


Using testcloud
===============


Creating a new instance
-----------------------

To create a new instance, you will need to provide the url of some cloud image in the *qcow2* format. If you do not have an image location of your own, you can use the image from the **Fedora Cloud** download pages (https://alt.fedoraproject.org/cloud/).

To create a new instance with the cloud image, run:

.. code:: bash

    testcloud instance create <instance name> -u <url for qcow2 image>

**testcloud** will download the *qcow2* image and save it in the ``/var/lib/testcloud/backingstores/<qcow2-filename>``. It will use this image a backing store for the newly created instance in ``/var/tmp/instances/<instance-name>``. When the image has been already downloaded, **testcloud** will use the previously download image to create the instance.

You will be able to see the instance using the ``list`` command. 

.. code:: bash

    testcloud instance list

Note, that the above command will only list the **running** instances. To see all instances, use:

.. code:: bash

   testcloud instance list --all 

Alternatively, the instances can also be viewed and manipulated using the **virt-manager** tool.


Starting, stopping, and removing an instance
--------------------------------------------

Instances can be started and stopped using the ``instance`` interface of the **testcloud**, too:

#. List all instances to see the correct name of the instance:

    .. code:: bash

        testcloud instance list --all

#. Start the instance:

    .. code:: bash

        testcloud instance start <instance-name>

#. Stop the instance:

    .. code:: bash

        testcloud instance stop <instance-name>

#. Remove the instance:

    .. code:: bash

        testcloud instance remove <instance-name>

Removing the instance only succeeds when the appropriate instance has been **stopped** before. However, you can use the ``-f`` option to force removing the instance. 

Other instance operations
-------------------------

#. Reboot the instance:

    .. code:: bash

        testcloud instance reboot <instance-name>

#. Remove non-existing libvirt VMs from testcloud:

    .. code:: bash
        
        testcloud instance clean

Logging into the instance
-------------------------

When the instance is created, **testcloud** will return its IP address that you can use to access the running instance via ``ssh``. The *login name* is ``fedora`` and the *password* is ``passw0rd``.

.. code:: bash

    ssh fedora@<instance-IP>

The IP address of an instance is also shown when you list the instance using the ``testcloud instance list`` command. You can also control the instance using the **virt-manager** tool.

Available options to create an instance
---------------------------------------

There are several options (all optional) that can be used to create a new instance using **testcloud**.

--ram RAM
    To set the amount of RAM that will be available to the virtual machine (in MiB).
--no-graphic
    This turns off the graphical display of the virtual machine.
--vnc
    To open a VNC connection at the ``:1`` display of the instance.
--atomic
    This flag should be used if the instance is booted from an Atomic Host.
-u, --url URL
    The URL from where the qcow2 image should be downloaded. **This option is compulsory.**
--timeout TIMEOUT
    A time (in seconds) to wait for boot to complete. Setting to 0 (default) will disable this functionality.
--disksize DISKSIZE
    To set the disk size of the virtual machine (in GiB)


Configuration
-------------

The default configuration should work for many people but those defaults can
be overridden through the use of a ``settings.py`` file containing the values to
use when overriding default settings. The example file in
``conf/settings-example.py`` shows the possible configuration values which can
be changed.

Note that in order for those new values to be picked up, the filename must be
``settings.py`` and that file must live in one of the following locations:

- ``conf/settings.py`` in the git checkout
- ``~/.config/testcloud/settings.py``
- ``/etc/testcloud/settings.py``

Testing
-------

There is a small testsuite you can run with:

.. code:: bash

    tox

This is a good place to contribute if you're looking to help out.

Issue Tracking and Roadmap
--------------------------

Our project tracker is on the Fedora QA-devel
`Pagure <https://pagure.io/testcloud//>`_
instance.

Credit
------

Thanks to `Oddshocks <https://github.com/oddshocks>`_ for the koji downloader code :)

License
-------

This code is licensed GPLv2+. See the LICENSE file for details.
