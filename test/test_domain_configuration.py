# -*- coding: utf-8 -*-
# Copyright 2025, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""Tests for domain configuration, specifically GraphicsConfiguration."""

from unittest.mock import patch

import peewee as pw

from testcloud import image
from testcloud.domain_configuration import (
    GraphicsConfiguration,
    _get_default_domain_conf,
)
from testcloud.sql import DBImage, DB

DB = pw.SqliteDatabase(":memory:")


class TestGraphicsConfiguration(object):

    def test_generate_spice(self):
        gc = GraphicsConfiguration(graphics_type="spice")
        xml = gc.generate()
        assert "<graphics type='spice' autoport='yes'/>" in xml
        assert "<model type='virtio'/>" in xml

    def test_generate_vnc(self):
        gc = GraphicsConfiguration(graphics_type="vnc")
        xml = gc.generate()
        assert "<graphics type='vnc' autoport='yes'/>" in xml

    def test_generate_with_listen_address(self):
        gc = GraphicsConfiguration(graphics_type="spice", listen_address="127.0.0.1")
        xml = gc.generate()
        assert "listen='127.0.0.1'" in xml

    def test_generate_without_listen_address(self):
        gc = GraphicsConfiguration(graphics_type="spice")
        xml = gc.generate()
        assert "listen=" not in xml


class TestDefaultDomainConfGraphics(object):

    def setup_method(self, method):
        DB.bind([DBImage], bind_refs=False, bind_backrefs=False)
        DB.connect()
        DB.create_tables([DBImage])
        self.patcher = patch('testcloud.sql.data_dir_changed', return_value=None)
        self.mocked_method = self.patcher.start()

    def teardown_method(self, method):
        self.patcher.stop()
        DB.drop_tables([DBImage])
        DB.close()

    def _make_image(self):
        return image.Image("file:///someimage.qcow2")

    def test_graphics_none(self):
        conf = _get_default_domain_conf("test-vm", self._make_image(), graphics="none")
        assert conf.graphics_configuration is None

    def test_graphics_spice(self):
        conf = _get_default_domain_conf("test-vm", self._make_image(), graphics="spice")
        assert conf.graphics_configuration is not None
        assert conf.graphics_configuration.graphics_type == "spice"

    def test_graphics_vnc(self):
        conf = _get_default_domain_conf("test-vm", self._make_image(), graphics="vnc")
        assert conf.graphics_configuration is not None
        assert conf.graphics_configuration.graphics_type == "vnc"

    def test_graphics_spice_system_listen_address(self):
        conf = _get_default_domain_conf(
            "test-vm", self._make_image(), graphics="spice", connection="qemu:///system")
        assert conf.graphics_configuration.listen_address == "127.0.0.1"

    def test_graphics_in_generated_xml(self):
        conf = _get_default_domain_conf("test-vm", self._make_image(), graphics="vnc")
        xml = conf.generate()
        assert 'type="vnc"' in xml
        assert "<video>" in xml

    def test_no_graphics_in_generated_xml(self):
        conf = _get_default_domain_conf("test-vm", self._make_image(), graphics="none")
        xml = conf.generate()
        assert "<graphics" not in xml
