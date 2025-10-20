from collections.abc import Callable
from functools import wraps
from inspect import Signature, iscoroutinefunction, signature
from typing import Any

from decorative_secrets._utilities import (
    get_function_signature_applicable_args_kwargs,
    get_signature_parameter_names_defaults,
    merge_function_signature_args_kwargs,
    unwrap_function,
)


def apply_conditional_defaults(
    condition: Callable[..., bool], *default_args: Any, **default_kwargs: Any
) -> Callable[..., Callable[..., Any]]:
    """
    This function decorates another function in order to apply a set of
    *default* keyword or positional/keyword argument values dependent on the
    outcome of passing an applicable subset of those arguments to the
    `condition` function.

    Parameters:
        condition: A function which accepts a subset of the decorated
            function's arguments and returns a boolean value indicating
            whether or not to apply the default argument values.
        *default_args: A set of positional argument values to apply as
            defaults if the condition is met.
        **default_kwargs: A set of keyword argument values to apply as
            defaults if the condition is met.

    Examples:
        ```python
        from decorative_secrets.defaults import apply_conditional_defaults


        @apply_conditional_defaults(
            lambda environment: environment == "prod",
            source_directory="/in/prod",
            target_directory="/out/prod",
        )
        @apply_conditional_defaults(
            lambda environment: environment == "dev",
            source_directory="/in/dev",
            target_directory="/out/dev",
        )
        @apply_conditional_defaults(
            lambda environment: environment == "stage",
            source_directory="/in/stage",
            target_directory="/out/stage",
        )
        def get_environment_source_target(
            environment: str = "dev",
            source_directory: str = "/dev/null",
            target_directory: str = "/dev/null",
        ) -> tuple[str, str, str]:
            return (environment, source_directory, target_directory)


        get_environment_source_target("stage")
        # ('stage', '/in/stage', '/out/stage')

        get_environment_source_target(environment="prod")
        # ('prod', '/in/prod', '/out/prod')

        get_environment_source_target()
        # ('dev', '/in/dev', '/out/dev')
        ```
    """

    def decorating_function(
        function: Callable[..., Any],
    ) -> Callable[..., Any]:
        original_function: Callable[..., Any] = unwrap_function(function)
        function_signature: Signature = signature(original_function)
        condition_signature: Signature = signature(condition)

        def get_args_kwargs(
            *args: Any, **kwargs: Any
        ) -> tuple[tuple[Any, ...], dict[str, Any]]:
            # First we consolidate the keyword arguments with any arguments
            # which are passed to parameters which can be either positional
            # *or* keyword arguments, and were passed as positional arguments
            args = merge_function_signature_args_kwargs(
                function_signature, args, kwargs
            )
            # Get the arguments and keyword arguments applicable to the
            # condition function
            condition_args: tuple[Any, ...]
            condition_kwargs: dict[str, Any]
            kwargs_or_defaults: dict[str, Any] = kwargs.copy()
            # Use function signature defaults for any missing keyword
            # parameters
            key: str
            value: Any
            for key, value in get_signature_parameter_names_defaults(
                function_signature
            ).items():
                if (
                    (value is None)
                    and (key in kwargs)
                    and (kwargs[key] is None)
                ):
                    # If the keyword argument value is explicitly `None`,
                    # and the parameter default is also `None`, we will infer
                    # a `None` default has been passed-through and drop it
                    # from the `kwargs` dictionary to allow the argument
                    # to be superseded by any applicable conditional defaults.
                    del kwargs[key]
                kwargs_or_defaults.setdefault(key, value)
            condition_args, condition_kwargs = (
                get_function_signature_applicable_args_kwargs(
                    condition_signature, args, kwargs_or_defaults
                )
            )
            if condition(*condition_args, **condition_kwargs):
                len_args: int = len(args)
                if len(default_args) > len_args:
                    # Extend args if there are more default args than args
                    args = (*args, *default_args[len_args:])
                kwargs.update(default_kwargs)
            return args, kwargs

        if iscoroutinefunction(function):

            @wraps(function)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                """
                This function wraps the original and applies conditional
                defaults
                """
                args, kwargs = get_args_kwargs(*args, **kwargs)
                # Execute the wrapped function
                return await function(*args, **kwargs)

        else:

            @wraps(function)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                """
                This function wraps the original and applies conditional
                defaults
                """
                args, kwargs = get_args_kwargs(*args, **kwargs)
                # Execute the wrapped function
                return function(*args, **kwargs)

        return wrapper

    return decorating_function
