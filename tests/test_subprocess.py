from __future__ import annotations

import subprocess
import sys
from contextlib import suppress
from subprocess import TimeoutExpired
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from decorative_secrets._utilities import (
    install_brew,
    which_brew,
    which_winget,
)
from decorative_secrets.errors import (
    HomebrewNotInstalledError,
)
from decorative_secrets.subprocess import (
    CalledProcessError,
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


def test_which_winget() -> None:
    """
    Verify that WinGet can be located on Windows.
    """
    if sys.platform.startswith("win"):
        winget: str = which_winget()
        assert check_output((winget, "--version"))


def test_install_brew_timeout_expires() -> None:
    """
    A near-zero `timeout` causes `install_brew` to raise `TimeoutExpired`
    rather than `HomebrewNotInstalledError`, proving `timeout` reaches the
    underlying `check_output` call.
    """
    if sys.platform == "darwin":
        with pytest.raises(TimeoutExpired):
            install_brew(timeout=1e-6)


def test_which_brew_timeout_expires() -> None:
    """
    A near-zero `timeout` causes `which_brew` to raise `TimeoutExpired`.
    """
    if sys.platform == "darwin":
        with pytest.raises(TimeoutExpired):
            which_brew(timeout=1e-6)


def test_which_winget_timeout_expires() -> None:
    """
    A near-zero `timeout` causes `which_winget` to raise `TimeoutExpired`.
    """
    if sys.platform.startswith("win"):
        with pytest.raises(TimeoutExpired):
            which_winget(timeout=1e-6)


_STDOUT_MARKER: str = "decorative-secrets-stdout-marker"
_STDERR_MARKER: str = "decorative-secrets-stderr-marker"


def _failing_command(script: str) -> tuple[str, ...]:
    """
    A command which runs `script` and exists on every supported platform.

    `bash` can't be used for this: on the Windows CI runners `bash`
    resolves to the WSL launcher (`C:\\Windows\\System32\\bash.exe`),
    which exits non-zero with its own error before ever running the
    script — so the command fails for the wrong reason, writing nothing
    to stderr.
    """
    return (sys.executable, "-c", script)


def _stderr_section(message: str) -> str:
    """
    The stderr which `CalledProcessError.__str__` appends, isolated from
    the command/exit-code portion of the message.

    Asserting a marker against the whole message would pass even when no
    stderr was captured at all, because the command repr in that message
    quotes the script — and therefore the marker — verbatim.
    """
    assert "Stderr:" in message
    return message.split("Stderr:", 1)[1].strip()


def test_check_call_suppresses_and_attaches_stderr(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    `check_call` suppresses a failing command's stderr from the console,
    attaches it to `error.stderr` as bytes, and includes it in
    `str(error)`.
    """
    with pytest.raises(CalledProcessError) as exc_info:
        check_call(
            _failing_command(
                f"import sys; sys.stderr.write({_STDERR_MARKER!r}); "
                f"sys.exit(3)"
            )
        )
    assert capfd.readouterr().err == ""
    error: CalledProcessError = exc_info.value
    assert isinstance(error, subprocess.CalledProcessError)
    assert isinstance(error.stderr, bytes)
    assert _STDERR_MARKER.encode() in error.stderr
    assert error.returncode == 3
    assert _stderr_section(str(error)) == _STDERR_MARKER


def test_check_output_error_str_includes_stderr() -> None:
    """
    `check_output` includes captured stderr in `str(error)` on failure.
    """
    with pytest.raises(CalledProcessError) as exc_info:
        check_output(
            _failing_command(
                f"import sys; sys.stderr.write({_STDERR_MARKER!r}); "
                f"sys.exit(1)"
            )
        )
    assert _stderr_section(str(exc_info.value)) == _STDERR_MARKER


def test_check_output_unsuppressed_error_str_includes_stderr() -> None:
    """
    With `suppress_stderr=False`, a failing command's stderr is still
    included in `str(error)`.
    """
    with pytest.raises(CalledProcessError) as exc_info:
        check_output(
            _failing_command(
                f"import sys; sys.stderr.write({_STDERR_MARKER!r}); "
                f"sys.exit(1)"
            ),
            suppress_stderr=False,
        )
    assert _stderr_section(str(exc_info.value)) == _STDERR_MARKER


def test_check_output_error_output_remains_bytes() -> None:
    """
    With `text=False`, a failing command's captured stdout is still
    attached to the error as `bytes` — rewriting the raise sites does not
    alter `error.output`.
    """
    with pytest.raises(CalledProcessError) as exc_info:
        check_output(
            _failing_command(
                f"import sys; sys.stdout.write({_STDOUT_MARKER!r}); "
                f"sys.stderr.write({_STDERR_MARKER!r}); sys.exit(1)"
            ),
            text=False,
        )
    error: CalledProcessError = exc_info.value
    assert isinstance(error.output, bytes)
    assert _STDOUT_MARKER.encode() in error.output


def test_called_process_error_str_truncates_long_stderr() -> None:
    """
    `str(error)` truncates stderr longer than the tail-length cap,
    keeping the *end* of the output — where the actionable error usually
    is — and marking the truncation.
    """
    with pytest.raises(CalledProcessError) as exc_info:
        check_output(
            _failing_command(
                f"import sys; "
                f"sys.stderr.write('e' * 20_000 + {_STDERR_MARKER!r}); "
                f"sys.exit(1)"
            )
        )
    stderr: str = _stderr_section(str(exc_info.value))
    assert stderr.startswith("...")
    # The tail is what survives truncation, not the head
    assert stderr.endswith(_STDERR_MARKER)
    assert len(stderr) < 15_000


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


def test_check_output_timeout_expires() -> None:
    """
    A `timeout` shorter than the command's runtime raises `TimeoutExpired`.
    """
    with pytest.raises(TimeoutExpired):
        check_output(("sleep", "5"), timeout=0.1)


def test_check_output_timeout_generous_succeeds() -> None:
    """
    A `timeout` longer than the command's runtime does not affect the
    result.
    """
    assert check_output(("echo", "hello"), timeout=5) == "hello"


def test_check_call_timeout_expires() -> None:
    """
    `check_call` forwards `timeout` to `check_output`, raising
    `TimeoutExpired` when exceeded.
    """
    with pytest.raises(TimeoutExpired):
        check_call(("sleep", "5"), timeout=0.1)


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
