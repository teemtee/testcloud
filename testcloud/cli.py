# -*- coding: utf-8 -*-
# Copyright 2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""
This is the primary user entry point for testcloud
"""

import argparse
import logging
import os
import sys
import libvirt
import requests
import re
from . import config
from . import image
from . import instance
from .exceptions import TestcloudPermissionsError, TestcloudInstanceError
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
    instances = instance.list_instances(args.connection)

    print("{!s:<16} {!s:^30}     {!s:<10}".format("Name", "IP", "State"))
    print("-"*60)
    for inst in instances:
        if args.all or inst['state'] == 'running':
            print("{!s:<27} {!s:^22}  {!s:<10}".format(inst['name'],
                                                       inst['ip'],
                                                       inst['state']))

    print("")

def _get_image_url(release_string):
    """
    Accepts re object with match in fedora:XX format (where XX can be number or 'latest' or 'qa_matrix')
    Returns url to Fedora Cloud qcow2
    """
    version = release_string.groups()[0]

    if version == "qa_matrix":
        try:
            nominated_response = requests.get("https://fedoraproject.org/wiki/Test_Results:Current_Installation_Test")
            return re.findall(r'href=\"(.*.x86_64.qcow2)\"', nominated_response.text)[0]
        except (ConnectionError, IndexError):
            print("Couldn't fetch the current image from qa_matrix ..")
            return None

    if version == "latest":
        try:
            latest_release = requests.get('https://packager.fedorainfracloud.org:5000/api/v1/releases').json()
        except (JSONDecodeError, ConnectionError):
            print("Couldn't fetch the latest Fedora release...")
            print("Expected format is 'fedora:XX' where XX is version number or 'latest' or 'qa_matrix'.")
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

def _create_instance(args):
    """Handler for 'instance create' command. Expects the following elements in args:
        * name(str)

    :param args: args from argparser
    """

    log.debug("create instance")

    image_by_name = re.match(r'fedora:(.*)', args.url)
    if image_by_name and "http" not in args.url and "file" not in args.url:
        url = _get_image_url(image_by_name)
        if not url:
            print("Couldn't find the desired image...")
            sys.exit(1)
        tc_image = image.Image(url)
    else:
        tc_image = image.Image(args.url)
    try:
        tc_image.prepare()
    except TestcloudPermissionsError as error:
        # User might not be part of testcloud group, print user friendly message how to fix this
        _handle_permissions_error_cli(error)

    existing_instance = instance.find_instance(args.name, image=tc_image,
                                               connection=args.connection)

    # can't create existing instances
    if existing_instance is not None:
        log.error("A testcloud instance named {} already exists at {}. Use 'testcloud instance start "
                "{}' to start the instance or remove it before re-creating.".format(
                    args.name,existing_instance.path, args.name)
             )
        sys.exit(1)

    else:
        tc_instance = instance.Instance(args.name, image=tc_image, connection=args.connection)

        # set ram size
        tc_instance.ram = args.ram

        # set disk size
        tc_instance.disk_size = args.disksize

        # prepare instance
        try:
            tc_instance.prepare()
        except TestcloudPermissionsError as error:
            _handle_permissions_error_cli(error)

        # create instance domain
        tc_instance.spawn_vm()

        # start created domain
        tc_instance.start(args.timeout)

        # find vm ip
        vm_ip = tc_instance.get_ip()

        # Write ip to file
        tc_instance.create_ip_file(vm_ip)
        print("The IP of vm {}:  {}".format(args.name, vm_ip))


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
    with open(os.path.join(config_data.DATA_DIR, 'instances', args.name, 'ip'), 'r') as ip_file:
        vm_ip = ip_file.read()
        print("The IP of vm {}:  {}".format(args.name, vm_ip))


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
    instarg_list = instarg_subp.add_parser("list", help="list instances")
    instarg_list.set_defaults(func=_list_instance)
    instarg_list.add_argument("--all",
                              help="list all instances, running and stopped",
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
                                help="name of instance to create")
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
                                     "eg. fedora:33, fedora:latest (latest Fedora GA image) or "
                                     "fedora:qa_matrix (image from https://fedoraproject.org/wiki/Test_Results:Current_Cloud_Test ) "
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
