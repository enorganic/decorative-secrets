from __future__ import annotations

import asyncio
import os
import sys
from collections import deque
from collections.abc import Coroutine
from contextlib import suppress
from functools import cache, partial, update_wrapper, wraps
from inspect import Parameter, Signature, signature
from io import TextIOWrapper
from shutil import which
from subprocess import (
    DEVNULL,
    PIPE,
    CalledProcessError,
    list2cmdline,
    run,
)
from traceback import format_exception
from typing import TYPE_CHECKING, Any
from urllib.request import urlopen

import nest_asyncio  # type: ignore[import-untyped]

from decorative_secrets.errors import (
    ArgumentsResolutionError,
    HomebrewNotInstalledError,
    WinGetNotInstalledError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from pathlib import Path


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


def check_output(
    args: tuple[str, ...],
    cwd: str | Path = "",
    input: str | bytes | None = None,  # noqa: A002
    env: Mapping[str, str] | None = None,
    *,
    echo: bool = False,
) -> str:
    """
    This function mimics `subprocess.check_output`, but redirects stderr
    to DEVNULL, and ignores unicode decoding errors.

    Parameters:

    - command (tuple[str, ...]): The command to run
    """
    if echo:
        if cwd:
            print("$", "cd", cwd, "&&", list2cmdline(args))  # noqa: T201
        else:
            print("$", list2cmdline(args))  # noqa: T201
    output: str = (
        run(
            args,
            stdout=PIPE,
            stderr=DEVNULL,
            check=True,
            cwd=cwd or None,
            input=input,
            env=env,
        )
        .stdout.rstrip()
        .decode("utf-8", errors="ignore")
    )
    if echo:
        print(output)  # noqa: T201
    return output


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


def remove_function_signature_inapplicable_kwargs(
    function_signature: Signature, kwargs: dict[str, Any]
) -> None:
    def get_parameter_name(parameter_: Parameter) -> str:
        return parameter_.name

    key: str
    for key in set(kwargs.keys()) - set(
        map(
            get_parameter_name,
            function_signature.parameters.values(),
        )
    ):
        del kwargs[key]


def get_function_signature_parameter_value_or_default(
    function_signature: Signature,
    parameter_name: str,
    kwargs: dict[str, Any],
    default: Any,
) -> Any:
    value: Any = default
    if parameter_name and (parameter_name in kwargs):
        value = kwargs[parameter_name] or default
    elif parameter_name in function_signature.parameters:
        value = (
            function_signature.parameters[parameter_name].default or default
        )
    return value


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


_FUNCTIONS_ERRORS: dict[int, dict[str, list[str]]] = {}


def _get_errors(function: Callable[..., Any]) -> dict[str, list[str]]:
    """
    This function retrieves the current function errors.
    """
    function_id: int = id(function)
    _FUNCTIONS_ERRORS.setdefault(function_id, {})
    return _FUNCTIONS_ERRORS[function_id]


def apply_callback_arguments(  # noqa: C901
    callback: Callable[..., Any] | None = None,
    async_callback: Callable[..., Any] | None = None,
    callback_parameter_names: Mapping[str, str]
    | Iterable[tuple[str, str]] = (),
    **callback_parameter_names_kwargs: str,
) -> Callable[..., Callable[..., Any]]:
    """
    This decorator maps parameter names to callback arguments.
    Each key represents the name of a parameter in the decorated function
    which accepts an explicit input, and the corresponding mapped value is
    an argument to pass to the provided callback function(s).

    Parameters:
        callback: A synchronous function which accepts one argument, and
            returns a value to be passed to a parameter of the decorated
            function.
        async_callback: An asynchronous function which accepts one argument,
            and returns a value to be passed to a parameter of the decorated
            function.
        callback_parameter_names:
            A mapping of static parameter names to callback parameter names.
        callback_parameter_names_kwargs: Synonymous with
            `callback_parameter_names`. When both are provided,
            `callback_parameter_names_kwargs` is updated from
            `callback_parameter_names` in order to merge the
            two.

    Returns:
        A decorator function which retrieves argument values by
            passing callback function arguments to the callback, and
            applying the output to their mapped static parameters.

    Examples:
        >>> @apply_callback_arguments(
        ...     lambda x: x * 2,
        ...     {"x": "x_lookup_args"},
        ... )
        ... def return_value(
        ...     x: int | None = None,
        ...     x_lookup_args: tuple[
        ...         Sequence[int],
        ...         Mapping[str, int],
        ...     ]
        ...     | None = None,
        ... ) -> int:
        ...     return x**2
        >>> return_value(
        ...     x_lookup_args=(
        ...         3,
        ...         None,
        ...     )
        ... )
        36
    """
    message: str
    if (callback is not None) and iscoroutinefunction(callback):
        raise TypeError(callback)
    if (async_callback is not None) and not iscoroutinefunction(
        async_callback
    ):
        raise TypeError(async_callback)
    if callback is None:
        if async_callback is None:
            message = (
                "Either a `callback` or an `async_callback` argument must be "
                "provided."
            )
            raise ValueError(message)

        def callback(argument: Any) -> Any:
            return asyncio_run(async_callback(argument))

    if async_callback is None:

        async def async_callback(argument: Any) -> Any:
            await asyncio.sleep(0)
            return callback(argument)

    if not isinstance(callback_parameter_names, dict):
        callback_parameter_names = dict(callback_parameter_names)
    if callback_parameter_names_kwargs:
        callback_parameter_names.update(**callback_parameter_names_kwargs)

    def decorating_function(  # noqa: C901
        function: Callable[..., Any],
    ) -> Callable[..., Any]:
        original_function: Callable[..., Any] = unwrap_function(function)
        function_signature: Signature = signature(original_function)

        def get_args_kwargs(  # noqa: C901
            *args: Any, **kwargs: Any
        ) -> tuple[tuple[Any, ...], dict[str, Any]]:
            """
            This function performs lookups for any parameters for which an
            argument is not passed explicitly.
            """
            # Capture errors
            errors: dict[str, list[str]] = _get_errors(original_function)
            # First we consolidate the keyword arguments with any arguments
            # which are passed to parameters which can be either positional
            # *or* keyword arguments, and were passed as positional arguments
            args = merge_function_signature_args_kwargs(
                function_signature, args, kwargs
            )
            # For any arguments where we have callback arguments and do not
            # have an explicitly passed value, execute the callback
            unused_callback_parameter_names: set[str] = set(
                callback_parameter_names.values()
            ) & set(kwargs.keys())
            parameter_name: str
            for parameter_name in set(callback_parameter_names.keys()) - set(
                kwargs.keys()
            ):
                callback_parameter_name: str = callback_parameter_names[
                    parameter_name
                ]
                unused_callback_parameter_names.discard(
                    callback_parameter_name
                )
                callback_argument: Any = kwargs.pop(
                    callback_parameter_name, None
                )
                parameter: Parameter | None = (
                    function_signature.parameters.get(parameter_name)
                )
                callback_: Callable[..., Any] = callback
                if (
                    (parameter is not None)
                    and (isinstance(parameter.annotation, type))
                    and issubclass(Coroutine, parameter.annotation)
                ):
                    callback_ = async_callback
                if callback_argument is not None:
                    try:
                        kwargs[parameter_name] = callback_(callback_argument)
                        # Clear preceding errors for this parameter
                        errors.pop(parameter_name, None)
                    except Exception:  # noqa: BLE001
                        errors.setdefault(parameter_name, [])
                        errors[parameter_name].append(get_exception_text())
                elif callback_parameter_name in function_signature.parameters:
                    default: tuple[Sequence[Any], Mapping[str, Any]] | None = (
                        function_signature.parameters[
                            callback_parameter_name
                        ].default
                    )
                    if default not in (Signature.empty, None):
                        try:
                            kwargs[parameter_name] = callback_(default)
                            # Clear preceding errors for this parameter
                            errors.pop(parameter_name, None)
                        except Exception:  # noqa: BLE001
                            errors.setdefault(parameter_name, [])
                            errors[parameter_name].append(get_exception_text())
                if (function is original_function) and errors:
                    arguments_error_messages: dict[str, list[str]] = {}
                    for key, argument_error_messages in errors.items():
                        # Don't raise an error for parameters which
                        # have a value or default value
                        if kwargs.get(key) is None:
                            parameter = function_signature.parameters.get(key)
                            if parameter and (
                                parameter.default is Signature.empty
                            ):
                                arguments_error_messages[key] = (
                                    argument_error_messages
                                )
                    # Clear global errors collection
                    del _FUNCTIONS_ERRORS[id(function)]
                    if arguments_error_messages:
                        raise ArgumentsResolutionError(
                            arguments_error_messages
                        )
            # Remove unused callback arguments
            deque(map(kwargs.pop, unused_callback_parameter_names), maxlen=0)
            # Remove arguments which do not correspond to
            # any of the function's parameter names
            remove_function_signature_inapplicable_kwargs(
                function_signature, kwargs
            )
            return (args, kwargs)

        if iscoroutinefunction(function):

            @wraps(function)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                """
                This function wraps the original and performs lookups for
                any parameters for which an argument is not passed
                """
                args, kwargs = get_args_kwargs(*args, **kwargs)
                # Execute the wrapped function
                return await function(*args, **kwargs)

        else:

            @wraps(function)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                """
                This function wraps the original and performs lookups for
                any parameters for which an argument is not passed
                """
                args, kwargs = get_args_kwargs(*args, **kwargs)
                # Execute the wrapped function
                return function(*args, **kwargs)

        return wrapper

    return decorating_function
