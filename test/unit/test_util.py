import logging
from unittest.mock import patch

from testcloud import util


def test_has_selinux_missing_command_does_not_configure_root_logging():
    root_logger = logging.getLogger()
    handlers = root_logger.handlers[:]

    try:
        root_logger.handlers = []

        with patch("testcloud.util.subprocess.call", side_effect=FileNotFoundError):
            assert util.has_selinux() is False

        assert root_logger.handlers == []
    finally:
        root_logger.handlers = handlers
