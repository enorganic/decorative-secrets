from asyncio import iscoroutinefunction
from collections.abc import Callable, Iterable, Iterator
from functools import wraps
from typing import Any, overload


def as_tuple(
    function: Callable[..., Iterable[Any]],
) -> Callable[..., Any]:
    """
    This is a decorator which will return an iterable as a tuple.

    Examples:
        ```python
        from decorative_secrets.utilities import as_tuple


        @as_tuple
        def get_numbers() -> Iterable[int]:
            yield 1
            yield 2
            yield 3


        assert get_numbers() == (1, 2, 3)
        ```
    """
    if iscoroutinefunction(function):

        @wraps(function)
        async def wrapper(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
            return tuple(await function(*args, **kwargs) or ())

    else:

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
            return tuple(function(*args, **kwargs) or ())

    return wrapper


@overload
def as_str(
    function: None = None,
    separator: str = "",
) -> Callable[..., Callable[..., str]]: ...


@overload
def as_str(
    function: Callable[..., Iterable[str]] = ...,
    separator: str = "",
) -> Callable[..., str]: ...


def as_str(
    function: Callable[..., Iterable[str]] | None = None,
    separator: str = "",
) -> Callable[..., Callable[..., str]] | Callable[..., str]:
    """
    This decorator causes a function yielding an iterable of strings to
    return a single string with the elements joined by the specified
    `separator`.

    Parameters:
        function: The function to decorate. If `None`, a decorating
            function is returned.
        separator: The string used to join the iterable elements.

    Returns:
        A decorator which joins the iterable elements into a single string.

    Examples:
        ```python
        from decorative_secrets.utilities import as_str


        @as_str(separator=", ")
        def get_fruits() -> Iterable[str]:
            yield "apple"
            yield "banana"
            yield "cherry"


        assert get_fruits() == "apple, banana, cherry"
        ```

        ```python
        from decorative_secrets.utilities import as_str


        @as_str
        def get_fruits() -> Iterable[str]:
            yield "apple\n"
            yield "banana\n"
            yield "cherry"


        assert get_fruits() == "apple\nbanana\ncherry"
        ```
    """

    def decorating_function(
        user_function: Callable[..., Iterable[str]],
    ) -> Callable[..., Any]:
        if iscoroutinefunction(user_function):

            @wraps(user_function)
            async def wrapper(*args: Any, **kwargs: Any) -> str:
                return separator.join(
                    await user_function(*args, **kwargs) or ()
                )

        else:

            @wraps(user_function)
            def wrapper(*args: Any, **kwargs: Any) -> str:
                return separator.join(user_function(*args, **kwargs) or ())

        return wrapper

    if function is None:
        return decorating_function
    return decorating_function(function)


def as_dict(
    function: Callable[..., Iterable[tuple[Any, Any]]],
) -> Callable[..., Any]:
    """
    This is a decorator which will return an iterable of key/value pairs
    as a dictionary.

    Examples:
        ```python
        from decorative_secrets.utilities import as_dict


        @as_dict
        def get_settings() -> Iterable[tuple[str, Any]]:
            yield ("host", "localhost")
            yield ("port", 8080)
            yield ("debug", True)


        assert get_settings() == (
            {"host": "localhost", "port": 8080, "debug": True}
        )
        ```
    """

    if iscoroutinefunction(function):

        @wraps(function)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[Any, Any]:
            return dict(await function(*args, **kwargs) or ())

    else:

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> dict[Any, Any]:
            return dict(function(*args, **kwargs) or ())

    return wrapper


def as_iter(
    function: Callable[..., Iterable[Any]],
) -> Callable[..., Any]:
    """
    This is a decorator which will return an iterator for a function
    yielding an iterable.

    Examples:
        ```python
        from decorative_secrets.utilities import as_iter
        from collections.abc import Iterator


        @as_iter
        def get_settings() -> Iterable[tuple[str, Any]]:
            yield ("host", "localhost")
            yield ("port", 8080)
            yield ("debug", True)


        assert issubclass(get_settings(), Iterator)
        ```
    """

    if iscoroutinefunction(function):

        @wraps(function)
        async def wrapper(*args: Any, **kwargs: Any) -> Iterator[Any]:
            return iter(await function(*args, **kwargs) or ())

    else:

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Iterator[Any]:
            return iter(function(*args, **kwargs) or ())

    return wrapper
