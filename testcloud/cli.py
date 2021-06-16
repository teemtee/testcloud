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
import random
import re
import requests
import string
import subprocess
import sys
import time

from . import config
from . import image
from . import instance
from .exceptions import TestcloudPermissionsError, TestcloudInstanceError

try:
    from simplejson.errors import JSONDecodeError
except ImportError:
    from json import JSONDecodeError

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

def _handle_connection_tip(instance, ip, port, vagrant=False):
    """
    Prints hint how to connect to the vm
    Prints detailed help for default config_data.USER_DATA and just the basic one for altered configurations
    """
    config_altered = False
    if config_data.USER_DATA != "#cloud-config\npassword: %s\nchpasswd: { expire: False }\nssh_pwauth: True\n    ":
        config_altered = True

    if not instance.backing_store:
        return

    if "coreos" in instance.backing_store.lower():
        kind = "CoreOs"
    elif "fedora" in instance.backing_store.lower():
        kind = "Fedora"
    elif "centos" in instance.backing_store.lower():
        if not vagrant:
            kind = "CentOS"
        else:
            kind = "cloud-user"
    else:
        # Let's use config_altered to indicate we don't detect an OS
        config_altered = True
    print("-"*60)
    if config_altered:
        print("To connect to the VM, use the following command:")
        if port == 22:
            print("ssh %s" % ip)
        else:
            print("ssh %s -p %d" % (ip, port))
    else:
        if kind == "Fedora":
            print("To connect to the VM, use the following command (password is '%s'):" % config_data.PASSWORD)
        elif kind == "CoreOs":
            print("To connect to the VM, use the following command :")
        if port == 22:
            print("ssh %s@%s" % (kind.lower(), ip))
        else:
            print("ssh %s@%s -p %d" % (kind.lower(), ip, port))
    if kind == "cloud-user":
        print("Due to limited support for Vagrant boxes, it may take up to 2 minutes for connection to be ready...")
    print("-"*60)

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
        if image_name.endswith(".qcow2"):
            images_in_use.add(image_name)
        else:
            # If we failed to obtain lock for image, bail out and do not remove anything later on
            raise subprocess.CalledProcessError

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

def _get_centos_image_url(version, stream=False):
    if stream:
        versions = config_data.CENTOS_STREAM_VERSIONS
    else:
        versions = config_data.CENTOS_VERSIONS

    if version in versions:
        return versions[version]
    else:
        print("Don't know requested CentOS version, allowed values are: %s" % str(versions.keys()))
        return None

def _get_fedora_image_url(version):
    """
    Accepts re object with match in fedora:XX format (where XX can be number or 'latest' or 'qa-matrix')
    Returns url to Fedora Cloud qcow2
    """
    # get coreos url
    if version in config_data.STREAM_LIST:
        try:
            result = requests.get("https://builds.coreos.fedoraproject.org/streams/%s.json"%version).json()
        except (ConnectionError, IndexError):
              print("Failed to fetch the image.")
              return None
        url = result['architectures']['x86_64']['artifacts']['qemu']['formats']['qcow2.xz']['disk']['location']

        return url
    #get testcloud url
    if version == "qa-matrix":
        try:
            nominated_response = requests.get("https://fedoraproject.org/wiki/Test_Results:Current_Installation_Test")
            return re.findall(r'href=\"(.*.x86_64.qcow2)\"', nominated_response.text)[0]
        except (ConnectionError, IndexError):
            print("Couldn't fetch the current image from qa-matrix ..")
            return None

    if version == "rawhide":
        stamp = 0
        try:
            releases = requests.get('https://openqa.fedoraproject.org/nightlies.json').json()
        except (ConnectionError, IndexError):
            print("Failed to fetch the image.")
            return None
        for release in releases:
            if release["arch"] == "x86_64" and release["subvariant"] == "Cloud_Base" and release["type"] == "qcow2":
                if release["mtime"] > stamp:
                    url = release["url"]
                    stamp = release["mtime"]
        return url

    if version == "latest":
        try:
            latest_release = requests.get('https://packager.fedorainfracloud.org:5000/api/v1/releases').json()
        except (JSONDecodeError, ConnectionError):
            print("Couldn't fetch the latest Fedora release...")
            print("Expected format is 'fedora:XX' where XX is version number or 'latest', 'rawhide' or 'qa-matrix'.")
            return None
        version = str(latest_release["fedora"]["stable"])

    try:
        releases = requests.get('https://getfedora.org/releases.json').json()
    except (JSONDecodeError, ConnectionError):
        print("Couldn't fetch releases list...")
        return None

    url = None
    for release in releases:
        if release["version"] == version and release["variant"] == "Cloud" and release["link"].endswith(".qcow2"):
            # Currently, we support just the x86_64
            if release["arch"] == "x86_64":
                url = release["link"]
                break

    return url

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

    if args.url and 'coreos' in args.url and not (args.ssh_path or args.ign_file or args.fcc_file):
        log.error("Missing --ssh_path/--ign_file/--fcc_file argument that's necessary for CoreOS.")
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

    no_url_coreos = False
    if not args.url:
        if not (args.ssh_path or args.ign_file or args.fcc_file):
            url = _get_fedora_image_url(config_data.VERSION)
        else:
            url = _get_fedora_image_url(config_data.STREAM)
            no_url_coreos = True
    elif "http" in args.url or "file" in args.url:
        url = args.url
    elif "fedora" in args.url:
        image_by_name = re.match(r'fedora:(.*)', args.url)
        stream_name_raw = re.match(r'fedora-coreos:(.*)', args.url)
        if image_by_name:
            version = image_by_name.groups()[0]
            url = _get_fedora_image_url(version)
        elif stream_name_raw:
            version = stream_name_raw.groups()[0]
            if version not in config_data.STREAM_LIST:
                log.error("fedora-coreos currently only have 'testing', 'stable', 'next' stream")
                sys.exit(1)
            else:
                url = _get_fedora_image_url(version)
    elif "centos-stream" in args.url:
        image_by_name = re.match(r'centos-stream:(.*)', args.url)
        version = image_by_name.groups()[0]
        url = _get_centos_image_url(version, True)
    elif "centos" in args.url:
        image_by_name = re.match(r'centos:(.*)', args.url)
        version = image_by_name.groups()[0]
        url = _get_centos_image_url(version, False)

    if not url:
        log.error("Couldn't find the desired image...")
        sys.exit(1)
    tc_image = image.Image(url)
    try:
        tc_image.prepare()
    except TestcloudPermissionsError as error:
        # User might not be part of testcloud group, print user friendly message how to fix this
        _handle_permissions_error_cli(error)

    if (not args.url and no_url_coreos) or (args.url and 'coreos' in args.url):
        log.debug("create coreos instance")
        tc_instance = instance.Instance(args.name, image=tc_image, connection=args.connection)
        # set ram size
        if not args.ram:
            tc_instance.ram = config_data.RAM_COREOS

        # set disk size
        if not args.disksize:
            tc_instance.disk_size = config_data.DISK_SIZE_COREOS

        tc_instance.ssh_path = args.ssh_path
        tc_instance.vcpus = args.vcpus
        tc_instance.fcc_file = args.fcc_file
        tc_instance.ign_file = args.ign_file
        tc_instance.coreos = True

    else:
        log.debug("create cloud instance")
        tc_instance = instance.Instance(args.name, image=tc_image, connection=args.connection)
        tc_instance.coreos = False

        # set ram size
        if not args.ram:
            tc_instance.ram = config_data.RAM

        # set disk size
        if not args.disksize:
            tc_instance.disk_size = config_data.DISK_SIZE

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

    if args.url.endswith(".box"):
        tc_instance.prepare_vagrant_init()

    # To workaround some ssh weirdness with CentOS/CentOS Stream, wait a while and reboot
    if "centos" in args.url or "centos-stream" in args.url:
        print("Waiting for instance to boot up to perform reboot for reliable SSH (%s seconds)..." % config_data.CENTOS_WAIT_REBOOT)
        time.sleep(config_data.CENTOS_WAIT_REBOOT)
        _stop_instance(args)
        _start_instance(args)

    # List connection details (for CentOS, we're doing the listing above in _start_instance)
    else:
        print("The IP of vm {}:  {}".format(args.name, vm_ip))
        print("The SSH port of vm {}:  {}".format(args.name, vm_port))
        _handle_connection_tip(tc_instance, vm_ip, vm_port, args.url.endswith(".box"))



def _start_instance(args):
    """Handler for 'instance start' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """
    log.debug("start instance: {}".format(args.name))

    tc_instance = instance.find_instance(args.name, connection=args.connection)

    if tc_instance is None:
        log.error("Cannot start instance {} because it does not exist".format(args.name))
        sys.exit(1)

    tc_instance.start(args.timeout)
    vm_ip = tc_instance.get_ip()
    vm_port = tc_instance.get_instance_port()
    print("The IP of vm {}:  {}".format(args.name, vm_ip))
    print("The SSH port of vm {}:  {}".format(args.name, vm_port))
    _handle_connection_tip(tc_instance, vm_ip, vm_port)


def _stop_instance(args):
    """Handler for 'instance stop' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """
    log.debug("stop instance: {}".format(args.name))

    tc_instance = instance.find_instance(args.name, connection=args.connection)

    if tc_instance is None:
        log.error("Cannot stop instance {} because it does not exist".format(args.name))
        sys.exit(1)

    tc_instance.stop()


def _remove_instance(args):
    """Handler for 'instance remove' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """
    log.debug("remove instance: {}".format(args.name))

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
    instarg_stop = instarg_subp.add_parser("stop", help="stop instance")
    instarg_stop.add_argument("name",
                              help="name of instance to stop")
    instarg_stop.set_defaults(func=_stop_instance)
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
    instarg_reboot = instarg_subp.add_parser("reboot", help="reboot instance")
    instarg_reboot.add_argument("name",
                                help="name of instance to reboot")
    instarg_reboot.add_argument("--timeout",
                                help="Time (in seconds) to wait for boot to "
                                "complete before completion, setting to 0"
                                " disables all waiting.",
                                type=int,
                                default=config_data.BOOT_TIMEOUT)
    instarg_reboot.set_defaults(func=_reboot_instance)
    # instance create
    instarg_create = instarg_subp.add_parser("create", help="create instance")
    instarg_create.set_defaults(func=_create_instance)
    instarg_create.add_argument("name",
                                help="name of instance to create",
                                nargs='?',
                                type=str,
                                default=None)
    instarg_create.add_argument("--ram",
                                help="Specify the amount of ram in MiB for the VM.",
                                type=int,
                                default=config_data.RAM)
    instarg_create.add_argument("--no-graphic",
                                help="Turn off graphical display.",
                                action="store_true")
    instarg_create.add_argument("--vnc",
                                help="Turns on vnc at :1 to the instance.",
                                action="store_true")
    instarg_create.add_argument("--atomic",
                                help="Use this flag if you're booting an Atomic Host.",
                                action="store_true")
    # this might work better as a second, required positional arg
    instarg_create.add_argument("-u",
                                "--url",
                                help="URL to qcow2 image or fedora:XX string is required. "
                                     "eg. fedora:rawhide (latest compose), fedora:33, fedora:latest (latest Fedora GA image) or "
                                     "fedora:qa-matrix (image from https://fedoraproject.org/wiki/Test_Results:Current_Cloud_Test ) "
                                     "are allowed values.",
                                type=str)
    instarg_create.add_argument("--timeout",
                                help="Time (in seconds) to wait for boot to "
                                     "complete before completion, setting to 0"
                                     " disables all waiting.",
                                type=int,
                                default=config_data.BOOT_TIMEOUT)
    instarg_create.add_argument("--disksize",
                                help="Desired instance disk size, in GB",
                                type=int,
                                default=config_data.DISK_SIZE)
    instarg_create.add_argument("--keep",
                                help="Don't remove instance from disk when something fails, useful for debugging",
                                action="store_true")
    instarg_create.add_argument("--ssh_path",
                                help="specify your ssh pubkey path",
                                type=str)
    instarg_create.add_argument("--fcc_file",
                                help="specify your fcc file path",
                                type=str)
    instarg_create.add_argument("--ign_file",
                                help="specify your ign file path",
                                type=str)
    instarg_create.add_argument("--vcpus",
                                help="vcpu number",
                                default=config_data.VCPUS)

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

    try:
        args.func(args)
    except AttributeError:
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
