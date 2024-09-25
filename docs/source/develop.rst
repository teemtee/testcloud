.. _development:

=====================
Testcloud Development
=====================

To develop **testcloud**, you need to perform a more complicated process to install all its dependencies, download the source code and perform a set-up.

Prerequisites
=============
#. Install the dependencies for testcloud.

    .. code-block:: bash

        $ sudo dnf builddep testcloud

#. Start ``libvirtd``.

    .. code-block:: bash

        $ sudo systemctl start libvirtd

#. Add the ``testcloud`` group to the system.

    .. code-block:: bash

        $ sudo groupadd testcloud

#. Add a user into the ``testcloud`` group.

    .. code-block:: bash

        $ sudo usermod -a -G testcloud $USER

#. Log out of the system and log in again to update the group information on your user or use a login shell on a different terminal.

    .. code-block:: bash

        $ su - $USER

Installation
============

#. Clone the testcloud repository.

    .. code-block:: bash

        $ git clone https://pagure.io/testcloud.git

#. Create the application directories.

    .. code-block:: bash

        $ sudo mkdir -p -m 775 /var/lib/testcloud

        $ sudo mkdir -p -m 775 /var/lib/testcloud/instances

        $ sudo mkdir -p -m 775 /var/lib/testcloud/backingstores

#. Change ownership on these directories to enable their use with testcloud.

    .. code-block:: bash

        $ sudo chown qemu:testcloud /var/lib/testcloud

        $ sudo chown qemu:testcloud /var/lib/testcloud/instances

        $ sudo chown qemu:testcloud /var/lib/testcloud/backingstores

#. Copy the ``.rules`` file to the ``polkit`` rules.

    .. code-block:: bash

        $ sudo cp conf/99-testcloud-nonroot-libvirt-access.rules /etc/polkit-1/rules.d/


Running testcloud
=================

#. Navigate to your testcloud git repository.

    .. code-block:: bash

        $ cd testcloud

#. Execute the ``run_testcloud.py`` script to run the testcloud. You can use any options as with the regular installation, for example:

    .. code-block:: bash

        $ ./run_testcloud.py instance create ...

.. tip::

    Alternatively, you can use **pip** to install testcloud onto the system and then use it like it has been installed normally.
    To do it, use the ``pip3 install -e . --user`` command in the project directory.


Testing
=======

There is a small test suite that you can run using ``tox``, to start the tests:

    .. code-block:: bash

        $ tox

Thank you very much for contributions.

