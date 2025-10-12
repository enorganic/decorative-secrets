from __future__ import annotations


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
