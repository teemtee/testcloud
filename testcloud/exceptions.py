# -*- coding: utf-8 -*-
# Copyright 2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""
Exceptions used with testcloud
"""


class TestcloudException(Exception):
    """Common ancestor for all Testcloud exceptions"""
    pass

class TestcloudImageError(TestcloudException):
    """Exception for errors having to do with images and image fetching"""
    pass

class TestcloudPermissionsError(TestcloudException):
    """Exception for errors from insufficient permissions on the file system."""
    pass

class TestcloudInstanceError(TestcloudException):
    """Exception for errors having to do with instances and instance prep"""
    pass


class DomainNotFoundError(Exception):
    """Exception to raise if the queried domain can't be found."""

    def __init__(self):
        self.value = "Could not find the requested virsh domain, did it register?"

    def __str__(self):
        return repr(self.value)
