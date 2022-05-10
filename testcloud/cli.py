# -*- coding: utf-8 -*-
# Copyright 2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""
This is the primary user entry point for testcloud
"""

import argparse
import libvirt
import logging
import os
import platform
import random
import re
import subprocess
import sys
import time

from . import config
from . import image
from . import instance
from .util import get_centos_image_url, get_fedora_image_url, get_ubuntu_image_url, get_ubuntu_releases, get_debian_image_url
from .exceptions import TestcloudImageError, TestcloudPermissionsError, TestcloudInstanceError


config_data = config.get_config()

# Only log to a file when specifically configured to
if config_data.LOG_FILE is not None:
    logging.basicConfig(filename=config_data.LOG_FILE, level=logging.DEBUG)

log = logging.getLogger('testcloud')
log.addHandler(logging.NullHandler())  # this is needed when running in library mode

description = """Testcloud is a small wrapper program designed to quickly and
simply boot images designed for cloud systems."""


################################################################################
# instance handling functions
################################################################################

def _handle_connection_tip(ip, port, vagrant=False):
    """
    Prints hint how to connect to the vm
    Prints detailed help for default config_data.USER_DATA and just the basic one for altered configurations
    """
    config_altered = False
    kind = ""

    if "#cloud-config\nssh_pwauth: true\npassword: %s\nchpasswd:\n  expire: false\n" not in config_data.USER_DATA:
        config_altered = True

    print("-"*60)
    if config_altered:
        print("To connect to the VM, use the following command:")
        if port == 22:
            print("ssh %s" % ip)
        else:
            print("ssh %s -p %d" % (ip, port))
    else:
        if kind in ["Fedora", "CentOS", "Ubuntu", "Debian"]:
            print("To connect to the VM, use the following command (password is '%s'):" % config_data.PASSWORD)
        elif kind == "CoreOS":
            print("To connect to the VM, use the following command :")
        if port == 22:
            print("ssh cloud-user@%s" % ip)
        else:
            print("ssh cloud-user@%s -p %d" % (ip, port))

    print("-"*60)

    if port != 22:
        print("Due to limitations of tescloud's user session VMs and bugs in some systems,"
              " the ssh connection may not be available immediately...")
    if vagrant:
        print("Due to limited support for images without cloud-init pre installed,"
              "it may take up to 2 minutes for connection to be ready...")

def _handle_permissions_error_cli(error):
    # User might not be part of testcloud group, print user friendly message how to fix this
    print(error)
    print("")
    print("You should be able to fix this by calling following commands:")
    print("sudo usermod -a -G testcloud $USER")
    print("su - $USER")
    sys.exit(1)

def _list_instance(args):
    """Handler for 'list' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """
    instances = instance.list_instances()

    if args.all:
        log.warning("(DEPRECATED) --all is now the default behavior")

    print("{!s:<16} {!s:^30} {!s:<10}    {!s:<10}".format("Name", "IP", "SSH Port", "State"))
    print("-"*80)
    for inst in instances:
        # Running first
        if inst['state'] == 'running':
            print("{!s:<27} {!s:^16} {!s:^12}  {!s:^14}".format(inst['name'],
                                                       inst['ip'],
                                                       inst['port'],
                                                       inst['state']))
    # And everything else
    for inst in instances:
        if inst['state'] != 'running':
            print("{!s:<27} {!s:^16} {!s:^12}  {!s:^14}".format(inst['name'],
                                                        inst['ip'],
                                                        inst['port'],
                                                        inst['state']))

    print("")


def _get_used_images(args):
    """
    Gets the list of images currently in use by any other instance
    """
    instances = instance.list_instances()

    # get images in use by any instance
    images_in_use = set()
    for inst in instances:
        path = os.path.join(config_data.DATA_DIR, "instances", inst["name"], inst["name"] + "-local.qcow2")
        command = "qemu-img info %s | grep 'backing file: '" % path
        image_name = subprocess.check_output(command , shell=True).decode().strip().replace("backing file: ", "")
        if image_name.endswith(".qcow2") or image_name.endswith(".img"):
            images_in_use.add(image_name)
        else:
            # If we failed to obtain lock for image, bail out and do not remove anything later on
            raise subprocess.CalledProcessError(1, None)

    return images_in_use


def _clean_backingstore(args):
    """
    Removes oldest files from config_data.STORE_DIR if the directory ocupies more than BACKINGSTORE_SIZE
    """
    max_size = int(config_data.BACKINGSTORE_SIZE) * 1024 * 1024 * 1024

    # Don't delete anything by default
    if max_size == 0:
        return

    # Bail erly if there are any running instances
    instances = instance.list_instances()
    running_instances = set()
    for inst in instances:
        if inst['state'] == "running":
            running_instances.add(inst["name"])
    if len(running_instances) > 0:
        print("")
        log.warn("Not proceeding with backingstore cleanup because there are some testcloud instances running.")
        print("You can fix this by following command(s):")
        for inst in running_instances:
            print("testcloud instance stop %s" % inst)
        print("")
        return

    try:
        images_in_use = _get_used_images(args)
    except subprocess.CalledProcessError:
        # Rather not clean anything if we can't be sure it's not used...
        print("Not proceeding with backingstore cleanup due to errors... Are all testcloud instances stopped?")
        return

    # create a list of all files in the `store_dir`
    files_by_mtime = []
    for file in os.listdir(config_data.STORE_DIR):
        fpath = os.path.join(config_data.STORE_DIR, file)
        ftime = os.path.getmtime(fpath)
        # Don't touch files created in the last 24 hours,
        if ftime >= (time.time() - 86400):
            continue
        # Don't touch images in use by any instance
        if file in images_in_use:
            continue
        # Touch only .qcow2 and .qcow2.part files
        if os.path.splitext(fpath)[1] not in ("qcow2", ".qcow2.part"):
            continue
        files_by_mtime.append((ftime, os.path.getsize(fpath), fpath))

    # sort descending by mtime
    files_by_mtime.sort(reverse=True)

    # remove files from the list before either:
    #  1) the sum of the removed files' sizes is larger than the BACKINGSTORE_SIZE
    #  2) you remove all the files from the list
    while True:
        try:
            _, size, _ = files_by_mtime[0]
        except IndexError:
            break

        # remove the current file's size from the allocated lot
        max_size -= size

        # if we just ran out of space, break free
        if max_size < 0:
            break

        # keep the file off of the 'remove me later on' list
        files_by_mtime.pop(0)

    # the files left in the list are to be deleted
    for _, _, fpath in files_by_mtime:
        os.remove(fpath)


def _generate_name():
    """
    Returns a random human-readable name
    """

    used_names = [inst["name"] for inst in instance._list_instances()]

    # Taken from https://github.com/moby/moby/blob/master/pkg/namesgenerator/names-generator.go
    left = ["admiring", "adoring", "affectionate", "agitated", "amazing", "angry", "awesome", "beautiful",
            "blissful", "bold", "boring", "brave", "busy", "charming", "clever", "cool", "compassionate",
            "competent", "condescending", "confident", "cranky", "crazy", "dazzling", "determined", "distracted",
            "dreamy", "eager", "ecstatic", "elastic", "elated", "elegant", "eloquent", "epic", "exciting",
            "fervent", "festive", "flamboyant", "focused", "friendly", "frosty", "funny", "gallant", "gifted",
            "goofy", "gracious", "great", "happy", "hardcore", "heuristic", "hopeful", "hungry", "infallible",
            "inspiring", "interesting", "intelligent", "jolly", "jovial", "keen", "kind", "laughing", "loving",
            "lucid", "magical", "mystifying", "modest", "musing", "naughty", "nervous", "nice", "nifty",
            "nostalgic", "objective", "optimistic", "peaceful", "pedantic", "pensive", "practical", "priceless",
            "quirky", "quizzical", "recursing", "relaxed", "reverent", "romantic", "sad", "serene", "sharp",
            "silly", "sleepy", "stoic", "strange", "stupefied", "suspicious", "sweet", "tender", "thirsty",
            "trusting", "unruffled", "upbeat", "vibrant", "vigilant", "vigorous", "wizardly", "wonderful",
            "xenodochial", "youthful", "zealous", "zen"]
    right = ["albattani", "allen", "almeida", "antonelli", "agnesi", "archimedes", "ardinghelli",
            "aryabhata", "austin", "babbage", "banach", "banzai", "bardeen", "bartik", "bassi",
            "beaver", "bell", "benz", "bhabha", "bhaskara", "black", "blackburn", "blackwell", "bohr",
            "booth", "borg", "bose", "bouman", "boyd", "brahmagupta", "brattain", "brown", "buck",
            "burnell", "cannon", "carson", "cartwright", "carver", "cerf", "chandrasekhar", "chaplygin",
            "chatelet", "chatterjee", "chebyshev", "cohen", "chaum", "clarke", "colden", "cori", "cray",
            "curran", "curie", "darwin", "davinci", "dewdney", "dhawan", "diffie", "dijkstra", "dirac",
            "driscoll", "dubinsky", "easley", "edison", "einstein", "elbakyan", "elgamal", "elion", "ellis",
            "engelbart", "euclid", "euler", "faraday", "feistel", "fermat", "fermi", "feynman", "franklin",
            "gagarin", "galileo", "galois", "ganguly", "gates", "gauss", "germain", "goldberg", "goldstine",
            "goldwasser", "golick", "goodall", "gould", "greider", "grothendieck", "haibt", "hamilton",
            "haslett", "hawking", "hellman", "heisenberg", "hermann", "herschel", "hertz", "heyrovsky",
            "hodgkin", "hofstadter", "hoover", "hopper", "hugle", "hypatia", "ishizaka", "jackson", "jang",
            "jemison", "jennings", "jepsen", "johnson", "joliot", "jones", "kalam", "kapitsa", "kare",
            "keldysh", "keller", "kepler", "khayyam", "khorana", "kilby", "kirch", "knuth", "kowalevski",
            "lalande", "lamarr", "lamport", "leakey", "leavitt", "lederberg", "lehmann", "lewin", "lichterman",
            "liskov", "lovelace", "lumiere", "mahavira", "margulis", "matsumoto", "maxwell", "mayer", "mccarthy",
            "mcclintock", "mclaren", "mclean", "mcnulty", "mendel", "mendeleev", "meitner", "meninsky", "merkle",
            "mestorf", "mirzakhani", "moore", "morse", "murdock", "moser", "napier", "nash", "neumann", "newton",
            "nightingale", "nobel", "noether", "northcutt", "noyce", "panini", "pare", "pascal", "pasteur",
            "payne", "perlman", "pike", "poincare", "poitras", "proskuriakova", "ptolemy", "raman", "ramanujan",
            "ride", "montalcini", "ritchie", "rhodes", "robinson", "roentgen", "rosalind", "rubin", "saha",
            "sammet", "sanderson", "satoshi", "shamir", "shannon", "shaw", "shirley", "shockley", "shtern",
            "sinoussi", "snyder", "solomon", "spence", "stonebraker", "sutherland", "swanson", "swartz",
            "swirles", "taussig", "tereshkova", "tesla", "tharp", "thompson", "torvalds", "tu", "turing",
            "varahamihira", "vaughan", "visvesvaraya", "volhard", "villani", "wescoff", "wilbur", "wiles",
            "williams", "williamson", "wilson", "wing", "wozniak", "wright", "wu", "yalow", "yonath", "zhukovsky"]

    name = "%s_%s" % (random.choice(left), random.choice(right))

    while name in used_names:
        name = "%s_%s" % (random.choice(left), random.choice(right))

    return name


def _create_instance(args):
    """Handler for 'instance create' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """

    try:
        _clean_backingstore(args)
    except (ValueError, PermissionError):
        # Cleanup errors aren't critical
        pass

    if not args.name:
        args.name = _generate_name()

    if args.url_legacy:
        log.error("This style of testcloud invocation has been REMOVED.")
        log.error("Instead of 'testcloud instance create -u <url>', do 'testcloud instance create <url>'.")
        log.error("You can specify instance name parameter with -n/--name argument.")
        sys.exit(1)

    if not args.url:
        log.error("Missing url or distribution:version specification.")
        log.error("Command to crate an instance: 'testcloud instance create <URL> or <distribution:version>'")
        log.error("                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^")
        log.error("You can use 'testcloud instance create -h' for additional help.")
        sys.exit(1)

    existing_instance = instance.find_instance(args.name, image=None,
                                               connection=args.connection)

    # can't create existing instances
    if existing_instance is not None:
        log.error("A testcloud instance named {} already exists at {}. Use 'testcloud instance start "
                "{}' to start the instance or remove it before re-creating.".format(
                    args.name,existing_instance.path, args.name)
             )
        sys.exit(1)

    url = None
    coreos = False

    if args.arch != "x86_64":
        log.warning("Testcloud might not work correctly on non-x86-64 machines yet.")

    if "http" in args.url or "file" in args.url:
        url = args.url
    elif "fedora" in args.url:
        image_by_name = re.match(r'fedora[:\-](.*)', args.url)
        stream_name_raw = re.match(r'fedora-coreos[:\-](.*)', args.url)
        # Normal Fedora Cloud
        if not "fedora-coreos" in args.url:
            version = image_by_name.groups()[0] if image_by_name else config_data.VERSION
            url = get_fedora_image_url(version, args.arch)
        # Fedora CoreOS
        else:
            version = stream_name_raw.groups()[0] if stream_name_raw else config_data.STREAM
            coreos = True
            if version not in config_data.STREAM_LIST:
                log.error("fedora-coreos currently only have 'testing', 'stable', 'next' stream")
                sys.exit(1)
            else:
                url = get_fedora_image_url(version, args.arch)
    elif "centos-stream" in args.url:
        image_by_name = re.match(r'centos-stream[:\-](.*)', args.url)
        version = image_by_name.groups()[0] if image_by_name else "latest"
        url = get_centos_image_url(version, True, args.arch)
    elif "centos" in args.url:
        image_by_name = re.match(r'centos[:\-](.*)', args.url)
        version = image_by_name.groups()[0] if image_by_name else "latest"
        url = get_centos_image_url(version, False, args.arch)
    elif "ubuntu" in args.url:
        image_by_name = re.match(r'ubuntu[:\-](.*)', args.url)
        version = image_by_name.groups()[0] if image_by_name else "latest"
        url = get_ubuntu_image_url(version, args.arch)
    elif "debian" in args.url:
        image_by_name = re.match(r'debian[:\-](.*)', args.url)
        version = image_by_name.groups()[0] if image_by_name else "latest"
        url = get_debian_image_url(version, args.arch)

    if not url:
        log.error("Couldn't find the desired image ( %s )..." % args.url)
        sys.exit(1)

    if "coreos" in url:
        coreos = True

    tc_image = image.Image(url)
    try:
        tc_image.prepare()
    except TestcloudPermissionsError as error:
        # User might not be part of testcloud group, print user friendly message how to fix this
        _handle_permissions_error_cli(error)
    except TestcloudImageError:
        log.error("Couldn't download the desired image (%s)..." % url)
        sys.exit(1)

    tc_instance = instance.Instance(args.name, image=tc_image, connection=args.connection, desired_arch=args.arch)

    # Normal Cloud
    if not coreos:
        log.debug("create cloud instance")
        tc_instance.coreos = False

        # set ram size
        tc_instance.ram = config_data.RAM if args.ram == -1 else args.ram

        # set disk size
        tc_instance.disk_size = config_data.DISK_SIZE if args.disksize == -1 else args.disksize

        # set vcpus
        tc_instance.vcpus = args.vcpus

    # CoreOS
    else:
        log.debug("create coreos instance")
        tc_instance.coreos = True

        # set ram size
        tc_instance.ram = config_data.RAM_COREOS if args.ram == -1 else args.ram

        # set disk size
        tc_instance.disk_size = config_data.DISK_SIZE_COREOS if args.disksize == -1 else args.disksize

        # set vcpus
        tc_instance.vcpus = args.vcpus

        tc_instance.ssh_path = args.ssh_path
        tc_instance.bu_file = args.bu_file
        tc_instance.ign_file = args.ign_file


    # prepare instance
    try:
        tc_instance.prepare()
    except TestcloudPermissionsError as error:
        _handle_permissions_error_cli(error)
    except TestcloudInstanceError as error:
        if args.keep:
            raise error
        else:
            tc_instance._remove_from_disk()

    # create instance domain
    try:
        tc_instance.spawn_vm()
    except libvirt.libvirtError:
        if not args.keep:
            tc_instance._remove_from_disk()
        log.error("An instance named {} already exists in libvirt. This might be broken testcloud instance or something else."
                "Fix the issues or use 'testcloud instance remove {}' to remove the instance and try again.".format(
                    args.name, args.name)
             )
        sys.exit(1)

    # start created domain
    try:
        tc_instance.start(args.timeout)
    except libvirt.libvirtError as error:
        # libvirt doesn't directly raise errors on boot failure
        # thus this happened before boot started
        if not args.keep:
            tc_instance._remove_from_disk()
            tc_instance._remove_from_libvirt()
        print("Failed when starting the virtual machine with:")
        raise error

    # find vm ip
    vm_ip = tc_instance.get_ip()
    # find vm port
    vm_port = tc_instance.get_instance_port()

    # Write ip to file
    tc_instance.create_ip_file(vm_ip)

    # CentOS .box files don't have cloud-init at all, others seem fine (eg. 1MT)
    cloud_init_missing = bool(re.search(r'centos-(.*)-vagrant-(.*)', args.url.lower()))
    if cloud_init_missing:
        tc_instance.prepare_vagrant_init()

    # List connection details
    print("The IP of vm {}:  {}".format(args.name, vm_ip))
    print("The SSH port of vm {}:  {}".format(args.name, vm_port))

    _handle_connection_tip(vm_ip, vm_port, cloud_init_missing)

def _domain_tip(args, action):
    connection = args.connection
    domains = {
        "qemu:///system": instance._prepare_domain_list(connection = "qemu:///system"),
        "qemu:///session": instance._prepare_domain_list(connection = "qemu:///session")
    }
    # We do the following check only for standard domains, not to break any (probaly not working anyway) wild deployments
    if args.name not in domains[connection].keys() and connection in domains.keys():
        del domains[connection]
        other_connection = list(domains.keys())[0]
        if args.name in domains[other_connection]:
            log.error("You have tried to %s a %s instance from a %s domain, "
                      "but it exists in %s domain." % (action, args.name, connection, other_connection))
            log.error("You can specify '-c %s' to %s this instance." % (other_connection, action))

            if action == "remove":
                if not "force" in args or args.force == False:
                    log.error("If your instances are in a broken state, use the -f parameter to try to proceed. Use this with caution!")
                    sys.exit(1)
            else:
                # We can't do the force arg in anything else than remove action, so exit unconditionally
                sys.exit(1)

def _start_instance(args):
    """Handler for 'instance start' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """
    log.debug("start instance: {}".format(args.name))
    _domain_tip(args, "start")

    tc_instance = instance.find_instance(args.name, connection=args.connection)

    if tc_instance is None:
        log.error("Cannot start instance {} because it does not exist".format(args.name))
        sys.exit(1)

    tc_instance.start(args.timeout)
    vm_ip = tc_instance.get_ip()
    vm_port = tc_instance.get_instance_port()
    print("The IP of vm {}:  {}".format(args.name, vm_ip))
    print("The SSH port of vm {}:  {}".format(args.name, vm_port))
    _handle_connection_tip(vm_ip, vm_port)


def _stop_instance(args):
    """Handler for 'instance stop' and 'instance force-off' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """
    log.debug("stop instance: {}".format(args.name))
    _domain_tip(args, "stop")

    tc_instance = instance.find_instance(args.name, connection=args.connection)

    if tc_instance is None:
        log.error("Cannot stop instance {} because it does not exist".format(args.name))
        sys.exit(1)

    tc_instance.stop(soft=False)

def _shutdown_instance(args, raise_e=False):
    """Handler for 'instance shutdown' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    :param raise_e: raises TestcloudInstanceError if True, catches it if False
    """
    log.debug("shutdown instance: {}".format(args.name))
    _domain_tip(args, "shutdown")

    tc_instance = instance.find_instance(args.name, connection=args.connection)

    if tc_instance is None:
        log.error("Cannot shutdown instance {} because it does not exist".format(args.name))
        sys.exit(1)

    try:
        tc_instance.stop(soft=True)
    except TestcloudInstanceError as e:
        log.error("Graceful shutdown failed, you might want to consider using 'instance force-off' command.")
        if raise_e:
            raise e


def _remove_instance(args):
    """Handler for 'instance remove' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """
    log.debug("remove instance: {}".format(args.name))
    _domain_tip(args, "remove")

    tc_instance = instance.find_instance(args.name, connection=args.connection)

    if tc_instance is None:
        log.error("Cannot remove instance {} because it does not exist".format(args.name))
        sys.exit(1)

    try:
        tc_instance.remove(autostop=args.force)
    except TestcloudInstanceError as e:
        log.error(e)
        sys.exit(1)


def _clean_instances(args):
    """Handler for 'instance clean' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """

    instance.clean_instances()


def _reboot_instance(args):
    """Handler for 'instance reboot' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """
    try:
        _shutdown_instance(args, raise_e=True)
    except TestcloudInstanceError:
        log.error("Graceful reboot failed, you might want to consider using 'instance reset' command.")
        sys.exit(1)
    _start_instance(args)

def _reset_instance(args):
    """Handler for 'instance reset' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """
    _stop_instance(args)
    _start_instance(args)


################################################################################
# image handling functions
################################################################################
def _list_image(args):
    """Handler for 'image list' command. Does not expect anything else in args.

    :param args: args from argparser
    """
    log.debug("list images")
    images = image.list_images()
    print("Current Images:")
    for img in images:
        print("  {}".format(img))


def _remove_image(args):
    """Handler for 'image remove' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """

    log.debug("removing image {}".format(args.name))

    tc_image = image.find_image(args.name)

    if tc_image is None:
        log.error("image {} not found, cannot remove".format(args.name))

    tc_image.remove()


def get_argparser():
    parser = argparse.ArgumentParser(description=description)
    subparsers = parser.add_subparsers(title="Command Types",
                                       description="Types of commands available",
                                       help="<command> --help")

    instarg = subparsers.add_parser("instance", help="help on instance options")
    instarg.add_argument("-c",
                         "--connection",
                         default="qemu:///system",
                         help="libvirt connection url to use")
    instarg_subp = instarg.add_subparsers(title="instance commands",
                                          description="Commands available for instance operations",
                                          help="<command> help")

    # instance list
    instarg_list = instarg_subp.add_parser("list", help="list all instances")
    instarg_list.set_defaults(func=_list_instance)
    instarg_list.add_argument("--all",
                              help="(DEPRECATED) --all is now the default behavior",
                              action="store_true")

    # instance start
    instarg_start = instarg_subp.add_parser("start", help="start instance")
    instarg_start.add_argument("name",
                               help="name of instance to start")
    instarg_start.add_argument("--timeout",
                               help="Time (in seconds) to wait for boot to "
                               "complete before completion, setting to 0"
                               " disables all waiting.",
                               type=int,
                               default=config_data.BOOT_TIMEOUT)
    instarg_start.set_defaults(func=_start_instance)

    # instance stop
    instarg_stop = instarg_subp.add_parser("stop", help="stop instance (forced poweroff, same as 'instance force-off')")
    instarg_stop.add_argument("name",
                              help="name of instance to stop")
    instarg_stop.set_defaults(func=_stop_instance)
    # instance force-off
    instarg_foff = instarg_subp.add_parser("force-off", help="force-off instance (forced poweroff, same as 'instance stop')")
    instarg_foff.add_argument("name",
                              help="name of instance to force-off")
    instarg_foff.set_defaults(func=_stop_instance)
    # instance shutdown
    instarg_shutdown = instarg_subp.add_parser("shutdown", help="shutdown instance (graceful poweroff)")
    instarg_shutdown.add_argument("name",
                              help="name of instance to shutdown")
    instarg_shutdown.set_defaults(func=_shutdown_instance)
    # instance remove
    instarg_remove = instarg_subp.add_parser("remove", help="remove instance")
    instarg_remove.add_argument("name",
                                help="name of instance to remove")
    instarg_remove.add_argument("-f",
                                "--force",
                                help="Stop the instance if it's running",
                                action="store_true")
    instarg_remove.set_defaults(func=_remove_instance)

    instarg_destroy = instarg_subp.add_parser("destroy", help="deprecated alias for remove")
    instarg_destroy.add_argument("name",
                                 help="name of instance to remove")
    instarg_destroy.add_argument("-f",
                                 "--force",
                                 help="Stop the instance if it's running",
                                 action="store_true")
    instarg_destroy.set_defaults(func=_remove_instance)

    # instance clean
    instarg_clean = instarg_subp.add_parser("clean", help="remove non-existing libvirt vms from testcloud")
    instarg_clean.set_defaults(func=_clean_instances)

    # instance reboot
    instarg_reboot = instarg_subp.add_parser("reboot", help="reboot instance (graceful reboot)")
    instarg_reboot.add_argument("name",
                                help="name of instance to reboot")
    instarg_reboot.add_argument("--timeout",
                                help="Time (in seconds) to wait for boot to "
                                "complete before completion, setting to 0"
                                " disables all waiting.",
                                type=int,
                                default=config_data.BOOT_TIMEOUT)
    instarg_reboot.set_defaults(func=_reboot_instance)
    # instance reset
    instarg_reset = instarg_subp.add_parser("reset", help="reset instance (forced reboot)")
    instarg_reset.add_argument("name",
                                help="name of instance to reset")
    instarg_reset.add_argument("--timeout",
                                help="Time (in seconds) to wait for boot to "
                                "complete before completion, setting to 0"
                                " disables all waiting.",
                                type=int,
                                default=config_data.BOOT_TIMEOUT)
    instarg_reset.set_defaults(func=_reset_instance)
    # instance create
    create_help = '''
    URL to qcow2 image or distro:release string is required.
    Examples of some known distro:release pairs:
    - fedora:rawhide (latest compose), fedora:33, fedora:latest (latest Fedora GA image)
    - fedora:qa-matrix (image from https://fedoraproject.org/wiki/Test_Results:Current_Cloud_Test )
    - centos:XX (eg. centos:8, centos:latest)
    - centos-stream:XX (eg. centos-stream:8, centos-stream:latest)
    - ubuntu:release_name (eg. ubuntu:focal, ubuntu:latest)
    - debian:release_name/release_number (eg. debian:11, debian:sid, debian:latest)
    '''
    instarg_create = instarg_subp.add_parser("create", help="create instance", formatter_class=argparse.RawTextHelpFormatter)
    instarg_create.set_defaults(func=_create_instance)
    instarg_create.add_argument("url",
                                help=create_help,
                                type=str,
                                nargs='?')
    instarg_create.add_argument("-u",
                                "--url",
                                help="REMOVED parameter, URL is now the first positional argument to testcloud instance create.",
                                type=str,
                                dest="url_legacy")
    instarg_create.add_argument("-n",
                                "--name",
                                help="name of instance to create",
                                type=str,
                                default=None)
    instarg_create.add_argument("-a",
                                "--arch",
                                help="desired architecture of an instance",
                                type=str,
                                default=platform.machine())
    instarg_create.add_argument("--ram",
                                help="Specify the amount of ram in MiB for the VM.",
                                type=int,
                                # Default value is handled in _create_instance (config_data.RAM or config_data.RAM_COREOS)
                                default=-1)
    instarg_create.add_argument("--vcpus",
                                help="Number of virtual CPU cores to assign to the VM.",
                                default=config_data.VCPUS)
    instarg_create.add_argument("--no-graphic",
                                help="Turn off graphical display.",
                                action="store_true")
    instarg_create.add_argument("--vnc",
                                help="Turns on vnc at :1 to the instance.",
                                action="store_true")
    instarg_create.add_argument("--timeout",
                                help="Time (in seconds) to wait for boot to "
                                     "complete before completion, setting to 0"
                                     " disables all waiting.",
                                type=int,
                                default=config_data.BOOT_TIMEOUT)
    instarg_create.add_argument("--disksize",
                                help="Desired instance disk size, in GB",
                                type=int,
                                # Same as with RAM few line above
                                default=-1)
    instarg_create.add_argument("--keep",
                                help="Don't remove instance from disk when something fails, useful for debugging",
                                action="store_true")
    instarg_create.add_argument("--ssh_path",
                                help="specify your ssh pubkey path",
                                type=str)
    instarg_create.add_argument("--bu_file",
                                help="specify your bu file path",
                                type=str)
    instarg_create.add_argument("--ign_file",
                                help="specify your ign file path",
                                type=str)

    imgarg = subparsers.add_parser("image", help="help on image options")
    imgarg_subp = imgarg.add_subparsers(title="subcommands",
                                        description="Types of commands available",
                                        help="<command> help")

    # image list
    imgarg_list = imgarg_subp.add_parser("list", help="list images")
    imgarg_list.set_defaults(func=_list_image)

    # image remove
    imgarg_remove = imgarg_subp.add_parser('remove', help="remove image")
    imgarg_remove.add_argument("name",
                               help="name of image to remove")
    imgarg_remove.set_defaults(func=_remove_image)

    imgarg_destroy = imgarg_subp.add_parser('destroy', help="deprecated alias for remove")
    imgarg_destroy.add_argument("name",
                                help="name of image to remove")
    imgarg_destroy.set_defaults(func=_remove_image)

    return parser


def _configure_logging(level=logging.DEBUG):
    '''Set up logging framework, when running in main script mode. Should not
    be called when running in library mode.

    :param int level: the stream log level to be set (one of the constants from logging.*)
    '''
    logging.basicConfig(format='%(levelname)s:%(message)s', level=level)


def main():
    parser = get_argparser()
    args = parser.parse_args()

    _configure_logging()

    if hasattr(args, "func"):
        args.func(args)
    else:
        # If no cmdline args were provided, func is missing
        # https://bugs.python.org/issue16308
        parser.print_help()
        sys.exit(1)


def find_vm_ip(name, connection='qemu:///system'):
    """Finds the ip of a local vm given its name used by libvirt.

    THIS METHOD IS DEPRECATED, PLEASE USE instance.Instance.get_ip() INSTEAD

    :param str name: name of the VM (as used by libvirt)
    :param str connection: name of the libvirt connection uri
    :returns: ip address of VM
    :rtype: str
    """

    log.warn('cli.find_vm_ip() is deprecated, please use '
             'instance.Instance.get_ip() instead')
    inst = instance.Instance('fake-instance')
    conn = libvirt.openReadOnly(connection)
    domain = conn.lookupByName(name)
    return inst.get_ip(domain=domain)
