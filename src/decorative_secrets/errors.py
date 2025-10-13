from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


class InterfaceNotInstalledError(RuntimeError):
    """
    Raised when a required CLI is not installed, and cannot be installed
    automatically.
    """

    def __init__(self, name: str, url: str | None = None) -> None:
        message: str = (
            f"Please install [{name}]({url})"
            if url
            else f"Please install {name}"
        )
        super().__init__(message)


class OnePasswordCommandLineInterfaceNotInstalledError(
    InterfaceNotInstalledError
):
    """
    Raised when the 1Password CLI is not installed, and cannot be installed
    automatically.
    """

    def __init__(self) -> None:
        super().__init__(
            "the 1Password CLI",
            "https://developer.1password.com/docs/cli/get-started/installation",
        )


class WinGetNotInstalledError(InterfaceNotInstalledError):
    """
    Raised when WinGet is not installed on a Windows system.
    """

    def __init__(self) -> None:
        super().__init__(
            "WinGet",
            "https://learn.microsoft.com/en-us/windows/package-manager/"
            "winget/",
        )


class HomebrewNotInstalledError(InterfaceNotInstalledError):
    """
    Raised when Homebrew is not installed on a macOS system.
    """

    def __init__(self) -> None:
        super().__init__(
            "Homebrew",
            "https://brew.sh/",
        )


class DatabricksCLINotInstalledError(InterfaceNotInstalledError):
    """
    Raised when the Databricks CLI is not installed, and cannot be installed
    automatically.
    """

    def __init__(self) -> None:
        super().__init__(
            "the Databricks CLI",
            "https://docs.databricks.com/aws/en/dev-tools/cli/install",
        )


def _iter_arguments_error_messages_lines(
    arguments_error_messages: dict[str, list[str]],
) -> Iterable[str]:
    parameter_name: str
    parameter_error_messages: list[str]
    is_first: bool = True
    for (
        parameter_name,
        parameter_error_messages,
    ) in arguments_error_messages.items():
        if not is_first:
            yield ""
        yield (
            "Errors were encountered looking up values for "
            f"`{parameter_name}`:\n"
        )
        yield from parameter_error_messages
        is_first = False


class ArgumentsResolutionError(ValueError):
    """
    Raised when one or more arguments cannot be resolved.
    """

    def __init__(self, arguments_error_messages: dict[str, list[str]]) -> None:
        super().__init__(
            "\n".join(
                _iter_arguments_error_messages_lines(arguments_error_messages)
            )
        )
