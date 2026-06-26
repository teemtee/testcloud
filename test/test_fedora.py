# -*- coding: utf-8 -*-
# Copyright 2026, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""Tests for Fedora version resolution via fedora-distro-aliases."""

from munch import Munch

from testcloud.distro_utils import fedora


def _distro(version, version_number):
    return Munch(version=version, version_number=version_number)


def _aliases(development, latest_stable):
    return {
        "fedora-development": development,
        "fedora-latest-stable": latest_stable,
    }


class TestResolveFedoraVersion:
    """``_resolve_fedora_version`` normalizes version strings using the
    aliases returned by ``fedora-distro-aliases``."""

    def test_numeric_rawhide(self):
        aliases = _aliases(
            development=[_distro("rawhide", "45")],
            latest_stable=[_distro("44", "44")],
        )
        assert fedora._resolve_fedora_version("45", aliases) == "rawhide"

    def test_numeric_branched(self):
        aliases = _aliases(
            development=[_distro("44", "44"), _distro("rawhide", "45")],
            latest_stable=[_distro("43", "43")],
        )
        assert fedora._resolve_fedora_version("44", aliases) == "branched"

    def test_latest_resolves_to_stable(self):
        aliases = _aliases(
            development=[_distro("rawhide", "45")],
            latest_stable=[_distro("44", "44")],
        )
        assert fedora._resolve_fedora_version("latest", aliases) == "44"

    def test_branched_falls_back_to_rawhide(self):
        aliases = _aliases(
            development=[_distro("rawhide", "45")],
            latest_stable=[_distro("44", "44")],
        )
        assert fedora._resolve_fedora_version("branched", aliases) == "rawhide"

    def test_rawhide_passthrough(self):
        aliases = _aliases(
            development=[_distro("rawhide", "45")],
            latest_stable=[_distro("44", "44")],
        )
        assert fedora._resolve_fedora_version("rawhide", aliases) == "rawhide"

    def test_numeric_passthrough(self):
        aliases = _aliases(
            development=[_distro("rawhide", "45")],
            latest_stable=[_distro("44", "44")],
        )
        assert fedora._resolve_fedora_version("43", aliases) == "43"

    def test_latest_without_stable(self):
        aliases = _aliases(
            development=[_distro("rawhide", "45")],
            latest_stable=[],
        )
        assert fedora._resolve_fedora_version("latest", aliases) == "latest"
