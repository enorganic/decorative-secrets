from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from decorative_secrets.errors import (
    ArgumentsResolutionError,
    DatabricksCLINotInstalledError,
    HomebrewNotInstalledError,
    InterfaceNotInstalledError,
    OnePasswordCommandLineInterfaceNotInstalledError,
    WinGetNotInstalledError,
    _iter_arguments_error_messages_lines,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def test_interface_not_installed_error_with_url() -> None:
    """
    When a URL is provided, the message renders it as a Markdown link.
    """
    error = InterfaceNotInstalledError("the Foo CLI", "https://example.com")
    assert str(error) == "Please install [the Foo CLI](https://example.com)"
    assert isinstance(error, RuntimeError)


def test_interface_not_installed_error_without_url() -> None:
    """
    When no URL is provided, the message names only the interface.
    """
    error = InterfaceNotInstalledError("the Foo CLI")
    assert str(error) == "Please install the Foo CLI"


@pytest.mark.parametrize(
    ("error_type", "expected_substring"),
    [
        (
            OnePasswordCommandLineInterfaceNotInstalledError,
            "the 1Password CLI",
        ),
        (WinGetNotInstalledError, "WinGet"),
        (HomebrewNotInstalledError, "Homebrew"),
        (DatabricksCLINotInstalledError, "the Databricks CLI"),
    ],
)
def test_concrete_interface_errors(
    error_type: Callable[[], InterfaceNotInstalledError],
    expected_substring: str,
) -> None:
    """
    Each concrete interface error is a subclass of
    `InterfaceNotInstalledError` and names its interface in the message.
    """
    error = error_type()
    assert isinstance(error, InterfaceNotInstalledError)
    assert expected_substring in str(error)
    # All concrete subclasses supply a documentation URL.
    assert "](" in str(error)


def test_iter_arguments_error_messages_lines_single_parameter() -> None:
    """
    For a single parameter, a header line precedes its error messages and
    no separator is emitted.
    """
    lines = list(
        _iter_arguments_error_messages_lines({"client_id": ["boom", "bang"]})
    )
    assert lines == [
        "Errors were encountered looking up values for `client_id`:\n",
        "boom",
        "bang",
    ]


def test_iter_arguments_error_messages_lines_multiple_parameters() -> None:
    """
    For multiple parameters, an empty separator line is emitted between
    parameter groups (but not before the first).
    """
    lines = list(
        _iter_arguments_error_messages_lines(
            {"client_id": ["e1"], "client_secret": ["e2"]}
        )
    )
    assert lines == [
        "Errors were encountered looking up values for `client_id`:\n",
        "e1",
        "",
        "Errors were encountered looking up values for `client_secret`:\n",
        "e2",
    ]


def test_arguments_resolution_error_message() -> None:
    """
    `ArgumentsResolutionError` joins the per-parameter lines into a single
    newline-delimited message and is a `ValueError`.
    """
    error = ArgumentsResolutionError({"client_id": ["could not read secret"]})
    assert isinstance(error, ValueError)
    assert (
        str(error)
        == "Errors were encountered looking up values for `client_id`:\n\n"
        "could not read secret"
    )


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
