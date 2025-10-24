from __future__ import annotations

import sys
from contextlib import suppress

import pytest

from decorative_secrets._utilities import (
    install_brew,
    which_brew,
)
from decorative_secrets.errors import (
    HomebrewNotInstalledError,
)
from decorative_secrets.subprocess import check_output


def test_install_brew() -> None:
    """
    Verify that the Homebrew install script can be downloaded and run on macOS.
    """
    if sys.platform == "darwin":
        # Here we supprcess the HomebrewNotInstalledError because the
        # correct behavior when running tests not in `sudo` mode is to fail
        # with this error
        with suppress(HomebrewNotInstalledError):
            install_brew()
            brew: str = which_brew()
            assert check_output((brew, "--version"))


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
