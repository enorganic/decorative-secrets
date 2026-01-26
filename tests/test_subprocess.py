from __future__ import annotations

import sys
from contextlib import suppress
from io import StringIO
from subprocess import CalledProcessError
from typing import TextIO

import pytest

from decorative_secrets._utilities import (
    install_brew,
    which_brew,
)
from decorative_secrets.errors import (
    HomebrewNotInstalledError,
)
from decorative_secrets.subprocess import check_call, check_output


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


def test_check_output() -> None:
    """
    Verify that the `check_output` function works as expected.
    """
    stderr: TextIO = sys.stderr
    with StringIO() as temp_stderr:
        sys.stderr = temp_stderr
        try:
            check_call(
                (
                    "bash",
                    "wtf",
                )
            )
        except CalledProcessError as error:
            temp_stderr.seek(0)
            if temp_stderr.read():
                pytest.raises(AssertionError)
            if not error.stderr.read():
                pytest.raises(AssertionError)
        finally:
            sys.stderr = stderr


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
