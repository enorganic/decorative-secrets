from collections.abc import Callable, Iterable
from functools import update_wrapper
from typing import Any


def as_tuple(
    user_function: Callable[..., Iterable[Any]],
) -> Callable[..., tuple[Any, ...]]:
    """
    This is a decorator which will return an iterable as a tuple.
    """

    def wrapper(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return tuple(user_function(*args, **kwargs) or ())

    return update_wrapper(wrapper, user_function)


def as_dict(
    user_function: Callable[..., Iterable[tuple[Any, Any]]],
) -> Callable[..., dict[Any, Any]]:
    """
    This is a decorator which will return an iterable of key/value pairs
    as a dictionary.
    """

    def wrapper(*args: Any, **kwargs: Any) -> dict[Any, Any]:
        return dict(user_function(*args, **kwargs) or ())

    return update_wrapper(wrapper, user_function)
