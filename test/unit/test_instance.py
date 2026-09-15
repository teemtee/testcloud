# -*- coding: utf-8 -*-
# Copyright 2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

""" This module is for testing the behaviour of the Image class."""

from unittest import mock
from unittest.mock import patch

import os
import peewee as pw


from testcloud import instance, image, config
from testcloud.sql import DBImage, DB

DB = pw.SqliteDatabase(":memory:")

class dotdict(dict):
    # https://stackoverflow.com/a/23689767
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


class TestInstance:

    def test_expand_qcow(self):
        pass

    def test_create_seed(self):
        pass

    def test_set_seed_path(self):
        pass

    def test_download_initrd_and_kernel(self):
        pass

    def test_boot_base(self):
        pass

    def test_boot_pristine(self):
        pass


class TestFindInstance(object):

    def setup_method(self, method):
        self.conf = config.ConfigData()
        DB.bind([DBImage], bind_refs=False, bind_backrefs=False)
        DB.connect()
        DB.create_tables([DBImage])
        self.patcher = patch('testcloud.sql.data_dir_changed', return_value=None)
        self.mocked_method = self.patcher.start()

    def teardown_method(self, method):
        DB.drop_tables([DBImage])
        DB.close()

    def test_non_existant_instance(self, monkeypatch):
        ref_name = "test-123"
        ref_image = image.Image("file:///someimage.qcow2")

        stub_listdir = mock.Mock()
        stub_listdir.return_value = []
        monkeypatch.setattr(os, "listdir", stub_listdir)

        test_instance = instance.find_instance(ref_name, ref_image)

        assert test_instance is None

    def test_find_exist_instance(self, monkeypatch):
        ref_name = "test-123"
        ref_image = image.Image("file:///someimage.qcow2")
        ref_path = os.path.join(self.conf.DATA_DIR, "instances/{}".format(ref_name))

        stub_listdir = mock.Mock()
        stub_listdir.return_value = [ref_name]
        monkeypatch.setattr(os, "listdir", stub_listdir)

        stub_data_dir = mock.Mock()
        stub_data_dir.return_value = dotdict({"DATA_DIR": self.conf.DATA_DIR})
        monkeypatch.setattr(config, "get_config", stub_data_dir)

        test_instance = instance.find_instance(ref_name, ref_image)

        assert test_instance.path == ref_path
