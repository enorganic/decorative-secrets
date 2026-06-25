from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from decorative_secrets.callback import (
    _get_sync_async_callbacks,
    apply_callback_arguments,
)
from decorative_secrets.errors import ArgumentsResolutionError


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


def test_no_callbacks_raises() -> None:
    """
    Providing no callbacks at all is an error.
    """
    with pytest.raises(ValueError, match="At least one callback"):
        apply_callback_arguments(x="x_lookup_arg")


def test_non_callable_callback_raises() -> None:
    """
    Providing only a non-callable (e.g. a mapping) yields neither a sync nor
    an async callback, which is an error.
    """
    with pytest.raises(ValueError, match="callback"):
        apply_callback_arguments({"not": "callable"}, x="x_lookup_arg")  # type: ignore[arg-type]


def test_get_sync_async_callbacks_wraps_sync_for_async() -> None:
    """
    Given only a synchronous callback, an asynchronous wrapper is generated
    which awaits to the same result.
    """

    def sync_callback(value: int) -> int:
        return value * 2

    _, async_callback = _get_sync_async_callbacks(sync_callback)
    assert asyncio.run(async_callback(3)) == 6


def test_get_sync_async_callbacks_wraps_async_for_sync() -> None:
    """
    Given only an asynchronous callback, a synchronous wrapper is generated
    which runs it to completion.
    """

    async def async_callback(value: int) -> int:
        await asyncio.sleep(0)
        return value * 2

    sync_callback, _ = _get_sync_async_callbacks(async_callback)
    assert sync_callback(3) == 6


def test_callback_applied_to_parameter_default() -> None:
    """
    When the lookup parameter is not supplied but has a (non-`None`) default,
    the callback is applied to that default value.
    """

    def callback(value: int) -> int:
        return value * 2

    @apply_callback_arguments(callback, x="x_lookup_arg")
    def return_value(
        x: int | None = None,
        x_lookup_arg: int | None = 5,  # noqa: ARG001
    ) -> int | None:
        return x

    assert return_value() == 10


def test_callback_error_on_default_is_swallowed_when_default_exists() -> None:
    """
    If the callback raises while resolving a parameter that has its own
    default, the error is recorded but not raised (the parameter simply
    keeps its default of `None`).
    """

    def callback(value: int) -> int:  # noqa: ARG001
        message = "boom"
        raise ValueError(message)

    @apply_callback_arguments(callback, x="x_lookup_arg")
    def return_value(
        x: int | None = None,
        x_lookup_arg: int | None = 5,  # noqa: ARG001
    ) -> int | None:
        return x

    assert return_value() is None


def test_callback_error_on_required_parameter_raises() -> None:
    """
    If the callback raises while resolving a parameter that has no default,
    the accumulated error is surfaced as an `ArgumentsResolutionError`.
    """

    def callback(value: int) -> int:  # noqa: ARG001
        message = "boom"
        raise ValueError(message)

    @apply_callback_arguments(callback, x="x_lookup_arg")
    def return_value(
        x: int,
        x_lookup_arg: int | None = None,  # noqa: ARG001
    ) -> int:
        return x

    with pytest.raises(ArgumentsResolutionError, match="`x`"):
        return_value(x_lookup_arg=3)


def test_callback_uses_async_callback_for_coroutine_annotation() -> None:
    """
    When the resolved parameter's runtime annotation is the `Coroutine`
    ABC, the asynchronous callback is selected, producing an awaitable
    result.

    `from __future__ import annotations` stringifies annotations, so the
    annotation is assigned as a real type before decoration to reproduce
    the condition the decorator checks for.
    """

    async def async_callback(value: int) -> int:
        await asyncio.sleep(0)
        return value * 2

    def return_value(
        value: Any = None,
        value_lookup: int | None = None,  # noqa: ARG001
    ) -> Any:
        return value

    return_value.__annotations__["value"] = Coroutine
    decorated = apply_callback_arguments(async_callback, value="value_lookup")(
        return_value
    )

    result = decorated(value_lookup=3)
    assert asyncio.iscoroutine(result)
    # Resolve the coroutine so it is not left un-awaited.
    assert asyncio.run(result) == 6


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
