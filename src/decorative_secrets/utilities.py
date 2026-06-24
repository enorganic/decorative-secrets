import asyncio
import inspect
import logging
import signal
import sys
import threading
from collections.abc import Awaitable, Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from functools import partial, wraps
from time import sleep
from traceback import format_exception
from typing import Any, Protocol, overload
from warnings import warn


def iscoroutinefunction(function: Any) -> bool:
    """
    An adaptation of `asyncio.iscoroutinefunction`
    """
    if isinstance(function, partial):
        return iscoroutinefunction(function.func)
    return (
        inspect.iscoroutinefunction(function)
        or type(getattr(function, "_is_coroutine", None)) is object
    )


def as_tuple(
    function: Callable[..., Iterable[Any] | Awaitable[Iterable[Any]]],
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
            return tuple(  # --
                await function(*args, **kwargs) or ()  # type: ignore[misc]
            )

    else:

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
            return tuple(
                function(*args, **kwargs) or ()  # type: ignore[arg-type]
            )

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
    function: Callable[..., Iterable[str]]
    | Awaitable[Iterable[Any]]
    | None = None,
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
                    await user_function(  # type: ignore[misc]
                        *args, **kwargs
                    )
                    or ()
                )

        else:

            @wraps(user_function)
            def wrapper(*args: Any, **kwargs: Any) -> str:
                return separator.join(user_function(*args, **kwargs) or ())

        return wrapper

    if function is None:
        return decorating_function
    return decorating_function(function)  # type: ignore[arg-type]


def as_dict(
    function: Callable[
        ..., Iterable[tuple[Any, Any]] | Awaitable[Iterable[tuple[Any, Any]]]
    ],
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
            return dict(
                await function(*args, **kwargs) or ()  # type: ignore[misc]
            )

    else:

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> dict[Any, Any]:
            return dict(
                function(*args, **kwargs) or ()  # type: ignore[arg-type]
            )

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
            return iter(
                await function(*args, **kwargs) or ()  # type: ignore[misc]
            )

    else:

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Iterator[Any]:
            return iter(function(*args, **kwargs) or ())

    return wrapper


def _default_retry_hook(
    error: Exception,
    attempt_number: int,  # noqa: ARG001
    *args: Any,  # noqa: ARG001
    **kwargs: Any,  # noqa: ARG001
) -> bool:
    """
    This is a retry hook which simply returns `True` for any error
    instance, allowing all retries to proceed.
    """
    if not error:
        raise ValueError(error)
    return True


class RetryHook(Protocol):
    def __call__(
        self, error: Exception, *args: Any, **kwargs: Any
    ) -> bool: ...


class AsyncRetryHook(Protocol):
    async def __call__(
        self, error: Exception, *args: Any, **kwargs: Any
    ) -> bool: ...


def warn_retry_hook(
    error: Exception,
    attempt_number: int,
    *args: Any,  # noqa: ARG001
    **kwargs: Any,  # noqa: ARG001
) -> bool:
    """
    This is a retry hook which will issue a warning and retry number
    whenever an error occurs.
    """
    message: str = f"Attempt # {attempt_number} failed with error: {error}"
    warn(
        message,
        stacklevel=2,
    )
    return True


def create_log_warning_retry_hook(
    logger: logging.Logger | Callable[[], logging.Logger],
) -> RetryHook:
    """
    This factory creates a retry hook which logs warning using the provided
    logger.

    Parameters:
        logger: The logger to use for logging warnings, or a callable which
        returns a logger.
    """
    if not isinstance(logger, logging.Logger) and callable(logger):
        logger = logger()
    if not isinstance(logger, logging.Logger):
        raise TypeError(logger)

    def retry_hook(
        error: Exception,
        attempt_number: int,
        *args: Any,  # noqa: ARG001
        **kwargs: Any,  # noqa: ARG001
    ) -> bool:
        logger.warning(
            "Attempt # %d failed with error: %s",
            attempt_number,
            str(error),
            stacklevel=2,
        )
        return True

    return retry_hook


def create_async_log_warning_retry_hook(
    logger: logging.Logger,
) -> AsyncRetryHook:
    """
    This factory creates an async retry hook which logs warning using the
    provided logger.

    !!! Note
        Please make sure to use a [non-blocking logger
        ](https://docs.python.org/3/howto/logging-cookbook.html#dealing-with-handlers-that-block).

    Parameters:
        logger: The logger to use for logging warnings.
    """

    async def retry_hook(
        error: Exception,
        attempt_number: int,
        *args: Any,  # noqa: ARG001
        **kwargs: Any,  # noqa: ARG001
    ) -> bool:
        logger.warning(
            "Attempt # %d failed with error: %s",
            attempt_number,
            str(error),
            stacklevel=2,
        )
        return True

    return retry_hook


def retry(  # noqa: C901
    errors: tuple[type[Exception], ...],
    retry_hook: RetryHook | AsyncRetryHook = _default_retry_hook,
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
        if iscoroutinefunction(function):

            @wraps(function)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                __attempt_number: int = kwargs.pop("__attempt_number", 1)
                if (number_of_attempts - __attempt_number) > 0:
                    # If `number_of_attempts` is greater than `attempt_number`,
                    # we have remaining attempts to try, so catch errors.
                    try:
                        return await function(*args, **kwargs)
                    except errors as error:
                        if not (
                            (
                                await retry_hook(  # type: ignore[misc]
                                    error, __attempt_number
                                )
                                if len(
                                    inspect.signature(retry_hook).parameters
                                )
                                > 1
                                else await retry_hook(  # type: ignore[misc]
                                    error
                                )
                            )
                            if iscoroutinefunction(retry_hook)
                            else (
                                retry_hook(error, __attempt_number)
                                if len(
                                    inspect.signature(retry_hook).parameters
                                )
                                > 1
                                else retry_hook(error)
                            )
                        ):
                            raise
                        await asyncio.sleep(2**__attempt_number)
                        __attempt_number += 1
                        return await wrapper(
                            *args, __attempt_number=__attempt_number, **kwargs
                        )
                # This is our last attempt, so just call the function.
                return await function(*args, **kwargs)

        else:

            @wraps(function)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                __attempt_number: int = kwargs.pop("__attempt_number", 1)
                if (number_of_attempts - __attempt_number) > 0:
                    try:
                        return function(*args, **kwargs)
                    except errors as error:
                        if not (
                            retry_hook(error, __attempt_number)
                            if len(inspect.signature(retry_hook).parameters)
                            > 1
                            else retry_hook(error)
                        ):
                            raise
                        sleep(2**__attempt_number)
                        __attempt_number += 1
                        return wrapper(
                            *args, __attempt_number=__attempt_number, **kwargs
                        )
                return function(*args, **kwargs)

        return wrapper

    return decorating_function


def _run_with_sigalrm_timeout(
    function: Callable,
    seconds: float,
    message: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """
    Run `function` synchronously, interrupting it with a `TimeoutError`
    via `SIGALRM` if it has not returned within `seconds`. This may only
    be used from the main thread of the main interpreter.
    """

    def handle_alarm(signal_number: int, frame: Any) -> None:  # noqa: ARG001
        raise TimeoutError(message)

    previous_handler = signal.signal(signal.SIGALRM, handle_alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return function(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _run_with_thread_pool_timeout(
    function: Callable,
    seconds: float,
    message: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """
    Run `function` in a worker thread, raising `TimeoutError` if it has
    not returned within `seconds`. The worker thread cannot be killed, so
    it continues to run to completion after the timeout is raised.
    """
    executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(function, *args, **kwargs)
        try:
            return future.result(timeout=seconds)
        except FuturesTimeoutError:
            raise TimeoutError(message) from None
    finally:
        # Do not wait: a timed-out worker thread may still be running.
        executor.shutdown(wait=False)


def timeout(seconds: float) -> Callable[[Callable], Callable]:
    """
    This is a decorator which enforces a maximum execution time on the
    decorated function. If the function does not return within `seconds`,
    a `TimeoutError` is raised.

    This works for both synchronous and asynchronous functions:

    -   Asynchronous functions are bounded using `asyncio.wait_for`, which
        cancels the coroutine on timeout.
    -   Synchronous functions are bounded using `signal.SIGALRM` when it is
        available and the call originates from the main thread, which
        interrupts the function in place.
    -   Otherwise (for example on Windows, or when called from a non-main
        thread), synchronous functions are run in a worker thread. The
        worker thread cannot be killed, so it continues running to
        completion after the `TimeoutError` is raised.

    Parameters:
        seconds: The maximum number of seconds to allow. Must be greater
            than zero.

    Examples:
        ```python
        from time import sleep

        from decorative_secrets.utilities import timeout


        @timeout(0.1)
        def slow() -> str:
            sleep(1)
            return "done"


        try:
            slow()
        except TimeoutError:
            print("timed out")
        ```
    """
    if seconds <= 0:
        raise ValueError(seconds)

    def decorating_function(function: Callable) -> Callable:
        message: str = (
            f"{function.__qualname__} timed out after {seconds} seconds"
        )
        if iscoroutinefunction(function):

            @wraps(function)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await asyncio.wait_for(
                        function(*args, **kwargs), timeout=seconds
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError(message) from None

        else:

            @wraps(function)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if hasattr(signal, "SIGALRM") and (
                    threading.current_thread() is threading.main_thread()
                ):
                    return _run_with_sigalrm_timeout(
                        function, seconds, message, args, kwargs
                    )
                return _run_with_thread_pool_timeout(
                    function, seconds, message, args, kwargs
                )

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
