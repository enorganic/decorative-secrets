import asyncio
from collections import deque
from collections.abc import Callable, Coroutine, Mapping, Sequence
from functools import wraps
from inspect import Parameter, Signature, signature
from typing import Any

from decorative_secrets._utilities import (
    _FUNCTIONS_ERRORS,
    asyncio_run,
    get_errors,
    iscoroutinefunction,
    merge_function_signature_args_kwargs,
    unwrap_function,
)
from decorative_secrets.errors import ArgumentsResolutionError
from decorative_secrets.utilities import get_exception_text


def _get_sync_async_callbacks(
    *callbacks: Callable[..., Any],
) -> tuple[Callable[..., Any], Callable[..., Any]]:
    """
    This function validates and consolidates a set of callback functions.
    """
    message: str
    if not callbacks:
        message = "At least one callback function must be provided."
        raise ValueError(message)
    sync_callback: Callable[..., Any] | None = None
    async_callback: Callable[..., Any] | None = None
    for callback in callbacks:
        if iscoroutinefunction(callback):
            async_callback = callback
        elif callable(callback):
            sync_callback = callback
    if sync_callback is None:
        if async_callback is None:
            message = (
                "Either a `callback` or an `async_callback` argument must be "
                "provided."
            )
            raise ValueError(message)

        def sync_callback(argument: Any) -> Any:
            return asyncio_run(async_callback(argument))

    if async_callback is None:

        async def async_callback(argument: Any) -> Any:
            await asyncio.sleep(0)
            return sync_callback(argument)

    return sync_callback, async_callback


def apply_callback_arguments(  # noqa: C901
    *callbacks: Callable[..., Any],
    **callback_parameter_names: str,
) -> Callable[..., Callable[..., Any]]:
    """
    This decorator maps parameter names to callback arguments.
    Each key represents the name of a parameter in the decorated function
    which accepts an explicit input, and the corresponding mapped value is
    an argument to pass to the provided callback function(s).

    Parameters:
        *callbacks: One or more callback functions. If both synchronous and
            asynchronous functions are provided, they will be used
            appropriately based on the decorated function's type, otherwise
            synchronous functions will be wrapped for asynchronous use
            and vice versa.
        **callback_parameter_names:
            A mapping of static parameter names to callback parameter names.

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
    callback: Callable[..., Any]
    async_callback: Callable[..., Any]
    callback, async_callback = _get_sync_async_callbacks(*callbacks)

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
            errors: dict[str, list[str]] = get_errors(original_function)
            # First we consolidate the keyword arguments with any arguments
            # which are passed to parameters which can be either positional
            # *or* keyword arguments, and were passed as positional arguments
            args = merge_function_signature_args_kwargs(
                function_signature, args, kwargs
            )
            # For any arguments where we have callback arguments and do not
            # have an explicitly passed value, execute the callback
            key: str
            value: Any
            used_keys: set[str] = {
                key for key, value in kwargs.items() if value is not None
            }
            unused_callback_parameter_names: set[str] = (
                set(callback_parameter_names.values()) & used_keys
            )
            parameter_name: str
            for parameter_name in (
                set(callback_parameter_names.keys()) - used_keys
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
