from __future__ import annotations

import asyncio

import pytest

from decorative_secrets.callback import apply_callback_arguments


def test_apply_callback_arguments() -> None:
    """
    Verify that the apply_callback_arguments decorator works as intended.
    """

    def callback(x: int) -> int:
        return x * 2

    @apply_callback_arguments(callback, x="x_lookup_arg")
    def return_value(
        x: int,
        x_lookup_arg: str | None = None,  # noqa: ARG001
    ) -> int:
        return x**2

    assert return_value(x_lookup_arg=3) == 36

    @apply_callback_arguments(callback, x="x_lookup_arg")
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

    @apply_callback_arguments(async_callback, x="x_lookup_arg")
    def return_value_with_async_callback(
        x: int,
        x_lookup_arg: str | None = None,  # noqa: ARG001
    ) -> int:
        return x**2

    assert return_value_with_async_callback(x_lookup_arg=3) == 36

    @apply_callback_arguments(async_callback, x="x_lookup_arg")
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


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
