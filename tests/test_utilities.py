from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from time import sleep
from typing import TYPE_CHECKING

import pytest

from decorative_secrets.utilities import (
    as_dict,
    as_iter,
    as_str,
    as_tuple,
    timeout,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


def test_as_dict() -> None:
    """
    Verify that the as_dict decorator works as intended.
    """

    @as_dict
    def get_key_value_pairs() -> Iterable[tuple[str, int]]:
        yield ("one", 1)
        yield ("two", 2)
        yield ("three", 3)

    assert get_key_value_pairs() == {"one": 1, "two": 2, "three": 3}


def test_as_iter() -> None:
    """
    Verify that the `as_iter` decorator works as intended.
    """

    @as_iter
    def get_key_value_pairs() -> Iterable[tuple[str, int]]:
        yield ("one", 1)
        yield ("two", 2)
        yield ("three", 3)

    assert isinstance(get_key_value_pairs(), Iterator)


def test_as_tuple() -> None:
    """
    Verify that the as_tuple decorator works as intended.
    """

    @as_tuple
    def get_numbers() -> Iterable[int]:
        yield 1
        yield 2
        yield 3

    assert get_numbers() == (1, 2, 3)


def test_as_str() -> None:
    """
    Verify that the as_str decorator works as intended.
    """

    @as_str(separator=", ")
    def get_fruits() -> Iterable[str]:
        yield "apple"
        yield "banana"
        yield "cherry"

    assert get_fruits() == "apple, banana, cherry"

    @as_str
    def get_vegetables() -> Iterable[str]:
        yield "carrot\n"
        yield "broccoli\n"
        yield "spinach"

    assert get_vegetables() == "carrot\nbroccoli\nspinach"


def test_timeout_sync_success() -> None:
    """
    A synchronous function which completes within the limit returns
    its value normally.
    """

    @timeout(1)
    def fast() -> str:
        return "ok"

    assert fast() == "ok"


def test_timeout_sync_expires() -> None:
    """
    A synchronous function which exceeds the limit raises `TimeoutError`.
    """

    @timeout(0.1)
    def slow() -> str:
        sleep(0.5)
        return "ok"

    with pytest.raises(TimeoutError):
        slow()


def test_timeout_async_success() -> None:
    """
    An asynchronous function which completes within the limit returns
    its value normally.
    """

    @timeout(1)
    async def fast() -> str:
        return "ok"

    assert asyncio.run(fast()) == "ok"


def test_timeout_async_expires() -> None:
    """
    An asynchronous function which exceeds the limit raises `TimeoutError`.
    """

    @timeout(0.1)
    async def slow() -> str:
        await asyncio.sleep(0.5)
        return "ok"

    with pytest.raises(TimeoutError):
        asyncio.run(slow())


def test_timeout_fallback_expires() -> None:
    """
    When the decorated function runs outside the main thread, the
    `SIGALRM` strategy is unavailable and the thread-pool fallback must
    still raise `TimeoutError`.
    """

    @timeout(0.1)
    def slow() -> str:
        sleep(0.5)
        return "ok"

    errors: list[BaseException] = []

    def run() -> None:
        try:
            slow()
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    assert len(errors) == 1
    assert isinstance(errors[0], TimeoutError)


def test_timeout_invalid_seconds() -> None:
    """
    A non-positive timeout raises `ValueError` at decoration time.
    """

    with pytest.raises(ValueError):  # noqa: PT011
        timeout(0)


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
