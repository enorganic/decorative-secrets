from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress
from functools import cache, partial, update_wrapper, wraps
from inspect import Parameter, Signature, signature
from io import TextIOWrapper
from shutil import which
from subprocess import (
    CalledProcessError,
)
from time import sleep
from traceback import format_exception
from typing import TYPE_CHECKING, Any
from urllib.request import urlopen
from warnings import warn

import nest_asyncio  # type: ignore[import-untyped]

from decorative_secrets.errors import (
    HomebrewNotInstalledError,
    WinGetNotInstalledError,
)
from decorative_secrets.subprocess import check_output
from decorative_secrets.utilities import as_dict

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable, Sequence


def iscoroutinefunction(function: Any) -> bool:
    if isinstance(function, partial):
        return iscoroutinefunction(function.func)
    return asyncio.iscoroutinefunction(function)


def get_exception_text() -> str:
    """
    When called within an exception, this function returns a text
    representation of the error matching what is found in
    `traceback.print_exception`, but is returned as a string value rather than
    printing.
    """
    return "".join(format_exception(*sys.exc_info()))


HOMEBREW_INSTALL_SH: str = (
    "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
)


def install_brew() -> None:
    """
    Install Homebrew on macOS or linux if not already installed.
    """
    env: dict[str, str] = os.environ.copy()
    env["NONINTERACTIVE"] = "1"
    bash: str = which("bash") or "/bin/bash"
    with TextIOWrapper(
        urlopen(HOMEBREW_INSTALL_SH)  # noqa: S310
    ) as response_io:
        try:
            check_output(
                (bash, "-c", response_io.read()),
                env=env,
            )
        except CalledProcessError as error:
            # This is usually because the script requires `sudo` access to run
            raise HomebrewNotInstalledError from error


@cache
def which_brew() -> str:
    """
    Find the `brew` executable on macOS, or install Homebrew if not found.
    """
    brew: str | None
    brew = which("brew") or "brew"
    try:
        check_output((brew, "--version"))
    except (CalledProcessError, FileNotFoundError):
        install_brew()
        brew = which("brew")
        if not brew:
            if sys.platform == "darwin":
                brew = "/opt/homebrew/bin/brew"
                if not os.path.exists(brew):
                    brew = "brew"
            else:
                brew = "/home/linuxbrew/.linuxbrew/bin/brew"
                if not os.path.exists(brew):
                    brew = "brew"
        try:
            check_output((brew, "--version"))
        except (CalledProcessError, FileNotFoundError) as error:
            raise HomebrewNotInstalledError from error
    return brew


@cache
def which_winget() -> str | None:
    """
    Find the `winget` executable on Windows, or raise an error if not found.
    """
    winget: str = which("winget") or "winget"
    try:
        check_output((winget, "--version"))
    except (CalledProcessError, FileNotFoundError) as error:
        raise WinGetNotInstalledError from error
    else:
        return winget


def as_tuple(
    user_function: Callable[..., Iterable[Any]],
) -> Callable[..., tuple[Any, ...]]:
    """
    This is a decorator which will return an iterable as a tuple.
    """

    def wrapper(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return tuple(user_function(*args, **kwargs) or ())

    return update_wrapper(wrapper, user_function)


@as_tuple
def merge_function_signature_args_kwargs(
    function_signature: Signature, args: Iterable[Any], kwargs: dict[str, Any]
) -> Iterable[Any]:
    """
    This function merges positional/keyword arguments for a function
    into the keyword argument dictionary, and returns any arguments which
    are positional-only.
    """
    value: Any
    parameter: Parameter
    if args:
        for parameter, value in zip(
            function_signature.parameters.values(), args, strict=False
        ):
            if parameter.kind == Parameter.POSITIONAL_OR_KEYWORD:
                kwargs[parameter.name] = value
            else:
                yield value


@as_dict
def get_signature_parameter_names_defaults(
    function_signature: Signature,
) -> Iterable[tuple[str, Any]]:
    """
    This function returns a dictionary mapping parameter names to their default
    values for all keyword parameters in the function signature.
    """
    parameter: Parameter
    for parameter in function_signature.parameters.values():
        if (parameter.default is not Signature.empty) and parameter.name:
            yield parameter.name, parameter.default


def get_function_signature_applicable_args_kwargs(
    function_signature: Signature | Callable,
    args: Sequence[Any],
    kwargs: dict[str, Any],
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """
    Given a function or function signature, and positional and keyword
    arguments, this function returns only those arguments and keyword
    arguments which are applicable to the function.

    Parameters:
        function_signature: A function or function signature whose
            parameters will be used to filter the provided arguments.
        args: A sequence of positional arguments.
        kwargs: A dictionary of keyword arguments.
    """
    applicable_kwargs: dict[str, Any] = {}
    max_positional_argument_count: int | None = 0
    parameter: Parameter
    if not isinstance(function_signature, Signature):
        function_signature = signature(function_signature)
    for parameter in function_signature.parameters.values():
        if parameter.kind == Parameter.VAR_KEYWORD:
            # All keywords are accepted
            applicable_kwargs = kwargs
            break
        if parameter.kind in (
            Parameter.KEYWORD_ONLY,
            Parameter.POSITIONAL_OR_KEYWORD,
        ) and (parameter.name in kwargs):
            applicable_kwargs[parameter.name] = kwargs[parameter.name]
        elif max_positional_argument_count is not None:
            if parameter.kind in (
                Parameter.POSITIONAL_ONLY,
                Parameter.POSITIONAL_OR_KEYWORD,
            ):
                max_positional_argument_count += 1
            elif parameter.kind == Parameter.VAR_POSITIONAL:
                # Unlimited positional arguments
                max_positional_argument_count = None
    return (tuple(args[:max_positional_argument_count]), applicable_kwargs)


def get_running_loop() -> asyncio.AbstractEventLoop | None:
    """
    Get the currently running event loop, or None if there is none.
    """
    loop: asyncio.AbstractEventLoop | None = None
    with suppress(RuntimeError):
        loop = asyncio.get_running_loop()
    return loop


def asyncio_run(coroutine: Coroutine) -> Any:
    """
    Run a coroutine, applying nest_asyncio if necessary.
    """
    loop: asyncio.AbstractEventLoop | None = get_running_loop()
    if loop is None:
        return asyncio.run(coroutine)
    nest_asyncio.apply(loop)
    return asyncio.run(coroutine)


def unwrap_function(
    function: Callable[..., Any],
) -> Callable:
    """
    This function retrieves the original, unwrapped, decorated function.
    """
    while hasattr(function, "__wrapped__"):
        function = function.__wrapped__
    return function


def _default_retry_hook(error: Exception) -> bool:
    if not error:
        raise ValueError(error)
    return True


def retry(  # noqa: C901
    errors: tuple[type[Exception], ...],
    retry_hook: Callable[[Exception], bool] = _default_retry_hook,
    number_of_attempts: int = 2,
) -> Callable:
    """
    This is a decorator which will retry a function a specified
    number of times if it raises one of the specified errors types.

    Parameters:
        errors: A tuple of exception types which should trigger a retry.
        retry_hook: A function which is called with the exception instance
            when an error occurs. If this function returns `False`, the
            exception is re-raised and no further retries are attempted.
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
                        if not retry_hook(error):
                            raise
                        warning_message: str = (
                            f"Attempt # {attempt_number!s}:\n"
                            f"{get_exception_text()}"
                        )
                        warn(warning_message, stacklevel=2)
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
                        if not retry_hook(error):
                            raise
                        warning_message: str = (
                            f"Attempt # {attempt_number!s}:\n"
                            f"{get_exception_text()}"
                        )
                        warn(warning_message, stacklevel=2)
                        sleep(2**attempt_number)
                        attempt_number += 1
                        return wrapper(*args, **kwargs)
                return function(*args, **kwargs)

        return wrapper

    return decorating_function


_FUNCTIONS_ERRORS: dict[int, dict[str, list[str]]] = {}


def _get_errors(function: Callable[..., Any]) -> dict[str, list[str]]:
    """
    This function retrieves the current function errors.
    """
    function_id: int = id(function)
    _FUNCTIONS_ERRORS.setdefault(function_id, {})
    return _FUNCTIONS_ERRORS[function_id]
