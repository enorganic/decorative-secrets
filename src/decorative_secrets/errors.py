from __future__ import annotations


class InterfaceNotInstalledError(RuntimeError):
    """
    Raised when a required CLI is not installed, and cannot be installed
    automatically.
    """

    def __init__(self, name: str, url: str | None = None) -> None:
        message: str = (
            f"Please install the [{name}]({url})"
            if url
            else f"Please install the {name}"
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
            "1Password CLI",
            "https://developer.1password.com/docs/cli/get-started/installation",
        )
