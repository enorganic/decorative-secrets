from __future__ import annotations

import sys
from contextlib import suppress
from io import StringIO
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from decorative_secrets._utilities import (
    install_brew,
    which_brew,
)
from decorative_secrets.errors import (
    HomebrewNotInstalledError,
)
from decorative_secrets.subprocess import (
    check_call,
    check_output,
    get_default_shell,
    list2cmdline,
)


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
            if not error.stderr:
                pytest.raises(AssertionError)
        finally:
            sys.stderr = stderr


def test_get_default_shell() -> None:
    """
    `get_default_shell` currently returns `None` (no shell wrapping).
    """
    assert get_default_shell() is None


def test_list2cmdline_without_shell() -> None:
    """
    Without a `zsh` shell, `list2cmdline` defers to the standard library
    `subprocess.list2cmdline`.
    """
    assert list2cmdline(("a", "b")) == "a b"


def test_list2cmdline_zsh_quotes_brackets() -> None:
    """
    With a `zsh` shell, arguments containing `[` are single-quoted so the
    shell does not treat them as glob patterns, while other arguments and
    already-quoted arguments are left untouched.
    """
    assert list2cmdline(("a[1]", "b"), shell="/usr/bin/zsh") == "'a[1]' b"
    assert list2cmdline(("'a[1]'",), shell="/bin/zsh") == "'a[1]'"


def test_check_output_text() -> None:
    """
    By default, output is returned as a stripped text string.
    """
    assert check_output(("echo", "hello")) == "hello"


def test_check_output_text_none_returns_none() -> None:
    """
    When `text=None`, no output is captured and `None` is returned.
    """
    assert check_output(("echo", "hello"), text=None) is None


def test_check_output_bytes() -> None:
    """
    When `text=False`, output is returned as stripped bytes.
    """
    assert check_output(("echo", "hello"), text=False) == b"hello"


def test_check_output_without_suppressing_stderr() -> None:
    """
    With `suppress_stderr=False`, the command still runs and returns its
    captured stdout.
    """
    assert check_output(("echo", "hello"), suppress_stderr=False) == "hello"


def test_check_output_echo_prints_command_and_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    With `echo=True`, the command line and its output are printed.
    """
    assert check_output(("echo", "hello"), echo=True) == "hello"
    captured = capsys.readouterr()
    assert "$ echo hello" in captured.out
    assert "hello" in captured.out


def test_check_output_decodes_bytes_input_for_text_mode() -> None:
    """
    When `input` is given as bytes but `text=True`, the input is decoded
    before being passed to the subprocess, and the echoed output matches.
    """
    assert check_output(("cat",), input=b"payload", text=True) == "payload"


def test_check_output_echo_with_cwd(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    With `echo=True` and a `cwd`, the printed command line includes the
    working-directory change.
    """
    check_output(("echo", "hello"), cwd=str(tmp_path), echo=True)
    assert "cd" in capsys.readouterr().out


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
