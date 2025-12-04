from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from decorative_secrets.utilities import as_dict, as_iter, as_str, as_tuple

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


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
