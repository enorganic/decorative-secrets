from __future__ import annotations

import asyncio
import sys
from contextlib import suppress
from subprocess import check_output

from decorative_secrets._utilities import (
    apply_callback_arguments,
    install_brew,
    install_databricks_cli,
    install_op,
    install_sh_databricks_cli,
    which_brew,
    which_op,
)
from decorative_secrets.errors import (
    HomebrewNotInstalledError,
    OnePasswordCommandLineInterfaceNotInstalledError,
)


def test_which_op() -> None:
    """
    Verify that the 1Password CLI is installed on invocation.
    """
    try:
        op: str = which_op()
        assert check_output((op, "--version"))
    except OnePasswordCommandLineInterfaceNotInstalledError:
        # The 1Password CLI should be possible to bootstrap on macOS and
        # Windows, but not Linux
        if sys.platform.startswith(("darwin", "win32")):
            raise


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


def test_install_sh_databricks_cli() -> None:
    """
    Verify that the Databricks CLI install script can be downloaded and run.
    """
    install_sh_databricks_cli()


def test_install_databricks_cli() -> None:
    """
    Verify that the Databricks CLI install script can be downloaded and run.
    """
    install_databricks_cli()


def test_install_op() -> None:
    """
    Verify that the 1Password CLI can be installed.
    """
    with suppress(OnePasswordCommandLineInterfaceNotInstalledError):
        install_op()
        op: str = which_op()
        assert check_output((op, "--version"))


def test_apply_callback_arguments() -> None:
    """
    Verify that the apply_callback_arguments decorator works as intended.
    """

    def callback(x: int) -> int:
        return x * 2

    @apply_callback_arguments(callback, None, {"x": "x_lookup_arg"})
    def return_value(
        x: int,
        x_lookup_arg: str | None = None,  # noqa: ARG001
    ) -> int:
        return x**2

    assert return_value(x_lookup_arg=3) == 36

    @apply_callback_arguments(callback, None, {"x": "x_lookup_arg"})
    async def async_return_value(
        x: int,
        x_lookup_arg: str | None = None,  # noqa: ARG001
    ) -> int:
        await asyncio.sleep(0)
        return x**2

    assert asyncio.run(async_return_value(x_lookup_arg=3)) == 36

    async def async_callback(x: int) -> int:
        await asyncio.sleep(0)
        return x * 2

    @apply_callback_arguments(None, async_callback, {"x": "x_lookup_arg"})
    def return_value_with_async_callback(
        x: int,
        x_lookup_arg: str | None = None,  # noqa: ARG001
    ) -> int:
        return x**2

    assert return_value_with_async_callback(x_lookup_arg=3) == 36

    @apply_callback_arguments(None, async_callback, {"x": "x_lookup_arg"})
    async def async_return_value_with_async_callback(
        x: int,
        x_lookup_arg: str | None = None,  # noqa: ARG001
    ) -> int:
        await asyncio.sleep(0)
        return x**2

    assert (
        asyncio.run(async_return_value_with_async_callback(x_lookup_arg=3))
        == 36
    )
