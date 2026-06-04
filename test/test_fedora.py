# -*- coding: utf-8 -*-
# Copyright 2026, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""Tests for Fedora release alias resolution via fedora-distro-aliases."""

from unittest.mock import patch

from munch import Munch

from testcloud.distro_utils import fedora


def _distro(version, version_number):
    return Munch(version=version, version_number=version_number)


def _aliases(development, latest_stable):
    return {
        "fedora-development": development,
        "fedora-latest-stable": latest_stable,
    }


class TestGetFedoraReleases:
    """``get_fedora_releases`` maps fedora-distro-aliases data to the
    oraculum-shaped ``{"rawhide", "branched", "stable"}`` dict."""

    def _run(self, aliases):
        with patch.object(fedora.config_data, "CACHE_IMAGES", False):
            with patch.object(fedora, "get_distro_aliases", return_value=aliases):
                return fedora.get_fedora_releases()

    def test_without_branched(self):
        aliases = _aliases(
            development=[_distro("rawhide", "45")],
            latest_stable=[_distro("44", "44")],
        )
        assert self._run(aliases) == {"rawhide": 45, "branched": None, "stable": 44}

    def test_with_branched(self):
        aliases = _aliases(
            development=[_distro("44", "44"), _distro("rawhide", "45")],
            latest_stable=[_distro("43", "43")],
        )
        assert self._run(aliases) == {"rawhide": 45, "branched": 44, "stable": 43}

    def test_without_stable(self):
        aliases = _aliases(
            development=[_distro("rawhide", "45")],
            latest_stable=[],
        )
        assert self._run(aliases) == {"rawhide": 45, "branched": None, "stable": None}
