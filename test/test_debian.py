# -*- coding: utf-8 -*-
# Copyright 2025, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""Tests for Debian cloud image URL generation."""

import pytest

from testcloud import config, exceptions
from testcloud.distro_utils import debian
from testcloud.distro_utils.debian import get_debian_image_url


PRIMARY = "https://cdimage.debian.org/images/cloud"
FALLBACK = "https://cloud.debian.org/images/cloud"


class TestGetDebianImageUrl(object):

    def setup_method(self, method):
        config._config = None

    def teardown_method(self, method):
        config._config = None

    def test_latest(self, monkeypatch):
        monkeypatch.setattr(config, "CONF_DIRS", [])
        urls = get_debian_image_url(version="latest", arch="x86_64")
        assert len(urls) == 2
        assert "bookworm" in urls[0]
        assert "genericcloud-amd64" in urls[0]
        assert urls[0].startswith(PRIMARY)
        assert urls[1].startswith(FALLBACK)

    def test_version_number(self, monkeypatch):
        monkeypatch.setattr(config, "CONF_DIRS", [])
        urls = get_debian_image_url(version="12", arch="x86_64")
        assert "bookworm" in urls[0]
        assert "debian-12-genericcloud" in urls[0]

    def test_codename(self, monkeypatch):
        monkeypatch.setattr(config, "CONF_DIRS", [])
        urls = get_debian_image_url(version="bookworm", arch="x86_64")
        assert "bookworm" in urls[0]
        assert "debian-12-genericcloud" in urls[0]

    def test_sid(self, monkeypatch):
        monkeypatch.setattr(config, "CONF_DIRS", [])
        urls = get_debian_image_url(version="sid", arch="x86_64")
        assert "sid/daily/latest/debian-sid-genericcloud-amd64-daily.qcow2" in urls[0]

    def test_invalid_version(self, monkeypatch):
        monkeypatch.setattr(config, "CONF_DIRS", [])
        with pytest.raises(exceptions.TestcloudImageError):
            get_debian_image_url(version="99", arch="x86_64")

    def test_unsupported_arch(self, monkeypatch):
        monkeypatch.setattr(config, "CONF_DIRS", [])
        with pytest.raises(exceptions.TestcloudImageError):
            get_debian_image_url(version="latest", arch="s390x")

    def test_aarch64_uses_generic(self, monkeypatch):
        monkeypatch.setattr(config, "CONF_DIRS", [])
        urls = get_debian_image_url(version="12", arch="aarch64")
        for url in urls:
            assert "generic-arm64" in url
            assert "genericcloud" not in url

    def test_str_config_compat(self, monkeypatch):
        monkeypatch.setattr(config, "CONF_DIRS", [])
        monkeypatch.setattr(debian.config_data, "DEBIAN_IMG_URL",
                            "https://example.com/%s/%s/%s.qcow2")
        urls = get_debian_image_url(version="12", arch="x86_64")
        assert len(urls) == 1
        assert urls[0].startswith("https://example.com/")

    def test_list_config(self, monkeypatch):
        monkeypatch.setattr(config, "CONF_DIRS", [])
        monkeypatch.setattr(debian.config_data, "DEBIAN_IMG_URL", [
            "https://mirror1.example.com/%s/%s/%s.qcow2",
            "https://mirror2.example.com/%s/%s/%s.qcow2",
            "https://mirror3.example.com/%s/%s/%s.qcow2",
        ])
        urls = get_debian_image_url(version="12", arch="x86_64")
        assert len(urls) == 3
        assert urls[0].startswith("https://mirror1")
        assert urls[2].startswith("https://mirror3")

    def test_no_config_mutation(self, monkeypatch):
        monkeypatch.setattr(config, "CONF_DIRS", [])
        cfg = config.get_config()
        original = list(cfg.DEBIAN_IMG_URL) if isinstance(cfg.DEBIAN_IMG_URL, list) else cfg.DEBIAN_IMG_URL

        get_debian_image_url(version="12", arch="aarch64")

        if isinstance(original, list):
            assert cfg.DEBIAN_IMG_URL == original
            for template in cfg.DEBIAN_IMG_URL:
                assert "genericcloud" in template
        else:
            assert cfg.DEBIAN_IMG_URL == original
            assert "genericcloud" in cfg.DEBIAN_IMG_URL
