from __future__ import annotations

import asyncio
from functools import wraps
from inspect import Signature, signature
from typing import Any

import pytest

from decorative_secrets._utilities import (
    asyncio_run,
    get_errors,
    get_function_signature_applicable_args_kwargs,
    get_running_loop,
    get_signature_parameter_names_defaults,
    merge_function_signature_args_kwargs,
    unwrap_function,
)


def test_merge_function_signature_args_kwargs() -> None:
    """
    Positional-or-keyword arguments are folded into `kwargs` in place, while
    positional-only arguments are returned as a tuple.
    """

    def function(a: int, b: int, /, c: int, d: int) -> None:
        """A function mixing positional-only and positional-or-keyword."""

    kwargs: dict[str, Any] = {}
    positional_only = merge_function_signature_args_kwargs(
        signature(function), (1, 2, 3, 4), kwargs
    )
    assert positional_only == (1, 2)
    assert kwargs == {"c": 3, "d": 4}


def test_merge_function_signature_args_kwargs_no_args() -> None:
    """
    With no positional arguments, nothing is merged and an empty tuple is
    returned.
    """

    def function(a: int, b: int) -> None:
        """A simple function."""

    kwargs: dict[str, Any] = {"a": 1}
    positional_only = merge_function_signature_args_kwargs(
        signature(function), (), kwargs
    )
    assert positional_only == ()
    assert kwargs == {"a": 1}


def test_get_signature_parameter_names_defaults() -> None:
    """
    Only parameters with defaults are returned, mapped to those defaults.
    """

    def function(a: int, b: int = 2, *, c: int = 3) -> None:
        """A function with default values."""

    defaults = get_signature_parameter_names_defaults(signature(function))
    assert defaults == {"b": 2, "c": 3}


def test_applicable_args_kwargs_filters_extras() -> None:
    """
    Surplus positional and keyword arguments which the function cannot
    accept are dropped.
    """

    def function(a: int, b: int, c: int) -> None:
        """A function accepting exactly three named parameters."""

    args, kwargs = get_function_signature_applicable_args_kwargs(
        function, (1, 2, 3, 4, 5), {"b": 20, "unexpected": 99}
    )
    # `b` was supplied as a keyword, so only `a` and `c` consume positions.
    assert args == (1, 2)
    assert kwargs == {"b": 20}


def test_applicable_args_kwargs_accepts_var_keyword() -> None:
    """
    A `**kwargs` parameter causes all keyword arguments to be accepted.
    """

    def function(a: int, **kwargs: Any) -> None:
        """A function accepting arbitrary keyword arguments."""

    _, kwargs = get_function_signature_applicable_args_kwargs(
        function, (1,), {"anything": 1, "everything": 2}
    )
    assert kwargs == {"anything": 1, "everything": 2}


def test_applicable_args_kwargs_accepts_var_positional() -> None:
    """
    A `*args` parameter lifts the cap on accepted positional arguments.
    """

    def function(*args: Any) -> None:
        """A function accepting arbitrary positional arguments."""

    args, _ = get_function_signature_applicable_args_kwargs(
        function, (1, 2, 3, 4), {}
    )
    assert args == (1, 2, 3, 4)


def test_applicable_args_kwargs_accepts_signature() -> None:
    """
    A `Signature` instance is accepted directly, not only a callable.
    """

    def function(a: int) -> None:
        """A single-parameter function."""

    function_signature: Signature = signature(function)
    args, _ = get_function_signature_applicable_args_kwargs(
        function_signature, (1, 2, 3), {}
    )
    assert args == (1,)


def test_get_running_loop_outside_loop() -> None:
    """
    Outside of any event loop, `get_running_loop` returns `None`.
    """
    assert get_running_loop() is None


def test_get_running_loop_inside_loop() -> None:
    """
    Inside a running event loop, `get_running_loop` returns that loop.
    """

    async def inside() -> asyncio.AbstractEventLoop | None:
        return get_running_loop()

    loop: asyncio.AbstractEventLoop | None = asyncio.run(inside())
    assert isinstance(loop, asyncio.AbstractEventLoop)


def test_asyncio_run_without_running_loop() -> None:
    """
    With no loop running, `asyncio_run` executes the coroutine and returns
    its result.
    """

    async def coroutine_function() -> str:
        return "ok"

    assert asyncio_run(coroutine_function()) == "ok"


def test_asyncio_run_within_running_loop() -> None:
    """
    When called from within a running loop, `asyncio_run` applies
    `nest_asyncio` so the nested coroutine can still run to completion.
    """

    async def inner() -> str:
        return "nested"

    async def outer() -> str:
        return asyncio_run(inner())

    assert asyncio.run(outer()) == "nested"


def test_unwrap_function() -> None:
    """
    `unwrap_function` returns the original function beneath any
    `functools.wraps` wrappers.
    """

    def original() -> str:
        return "original"

    @wraps(original)
    def wrapper() -> str:
        return original()

    assert unwrap_function(wrapper) is original


def test_unwrap_function_without_wrapping() -> None:
    """
    An unwrapped function is returned unchanged.
    """

    def plain() -> None:
        """An undecorated function."""

    assert unwrap_function(plain) is plain


def test_get_errors_returns_shared_mutable_mapping() -> None:
    """
    `get_errors` returns the same mutable mapping for a given function across
    calls, so accumulated errors persist.
    """

    def function() -> None:
        """A function used purely as an error-registry key."""

    errors = get_errors(function)
    errors.setdefault("client_id", []).append("Dummy Error")
    assert get_errors(function) == {"client_id": ["Dummy Error"]}


def test_get_errors_distinct_per_function() -> None:
    """
    Distinct functions receive distinct error mappings.
    """

    def first() -> None:
        """First registry key."""

    def second() -> None:
        """Second registry key."""

    get_errors(first)["a"] = ["x"]
    assert "a" not in get_errors(second)


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
