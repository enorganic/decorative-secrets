import asyncio
import inspect
import sys
from asyncio import iscoroutinefunction
from collections.abc import Callable, Iterable, Iterator
from functools import wraps
from time import sleep
from traceback import format_exception
from typing import Any, Protocol, overload


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


def _default_retry_hook(
    error: Exception,
    attempt_number: int,  # noqa: ARG001
) -> bool:
    if not error:
        raise ValueError(error)
    return True


class _RetryHook(Protocol):
    def __call__(
        self, error: Exception, *args: Any, **kwargs: Any
    ) -> bool: ...


class _AsyncRetryHook(Protocol):
    async def __call__(
        self, error: Exception, *args: Any, **kwargs: Any
    ) -> bool: ...


def retry(  # noqa: C901
    errors: tuple[type[Exception], ...],
    retry_hook: _RetryHook | _AsyncRetryHook = _default_retry_hook,
    number_of_attempts: int = 2,
) -> Callable:
    """
    This is a decorator which will retry a function a specified
    number of times, with exponential backoff, if it raises one of the
    specified errors types.

    Parameters:
        errors: A tuple of exception types which should trigger a retry.
        retry_hook: A function which is called with the exception instance
            (optionally) and an attempt number when an error occurs. If this
            function returns `False`, the exception is re-raised and no further
            retries are attempted.
        number_of_attempts: The total number of attempts to make, including
            the initial attempt.
    """

    def decorating_function(function: Callable) -> Callable:
        attempt_number: int = 1
        if iscoroutinefunction(function):

            @wraps(function)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                nonlocal attempt_number
                if number_of_attempts - attempt_number:
                    # If `number_of_attempts` is greater than `attempt_number`,
                    # we have remaining attempts to try, so catch errors.
                    try:
                        return await function(*args, **kwargs)
                    except errors as error:
                        if not (
                            (
                                await retry_hook(error, attempt_number)
                                if len(
                                    inspect.signature(retry_hook).parameters
                                )
                                > 1
                                else await retry_hook(error)
                            )
                            if iscoroutinefunction(retry_hook)
                            else (
                                retry_hook(error, attempt_number)
                                if len(
                                    inspect.signature(retry_hook).parameters
                                )
                                > 1
                                else retry_hook(error)
                            )
                        ):
                            raise
                        await asyncio.sleep(2**attempt_number)
                        attempt_number += 1
                        return await wrapper(*args, **kwargs)
                # This is our last attempt, so just call the function.
                return await function(*args, **kwargs)

        else:

            @wraps(function)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                nonlocal attempt_number
                if number_of_attempts - attempt_number:
                    try:
                        return function(*args, **kwargs)
                    except errors as error:
                        if not (
                            retry_hook(error, attempt_number)
                            if len(inspect.signature(retry_hook).parameters)
                            > 1
                            else retry_hook(error)
                        ):
                            raise
                        sleep(2**attempt_number)
                        attempt_number += 1
                        return wrapper(*args, **kwargs)
                return function(*args, **kwargs)

        return wrapper

    return decorating_function


def get_exception_text() -> str:
    """
    When called within an exception, this function returns a text
    representation of the error matching what is found in
    `traceback.print_exception`, but is returned as a string value rather than
    printing.
    """
    return "".join(format_exception(*sys.exc_info()))
