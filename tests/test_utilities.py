from __future__ import annotations

import asyncio
import sys
from contextlib import suppress

from decorative_secrets._utilities import (
    install_brew,
    which_brew,
)
from decorative_secrets.callback import apply_callback_arguments
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
