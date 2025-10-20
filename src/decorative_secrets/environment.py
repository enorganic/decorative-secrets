from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any

from decorative_secrets.callback import apply_callback_arguments

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


async def _async_getenv(env: Mapping[str, str], name: str) -> str | None:
    return await asyncio.to_thread(env.__getitem__, name)


def _getenv(env: Mapping[str, str], name: str) -> str | None:
    return env[name]


@dataclass(frozen=True)
class ApplyEnvironmentArgumentsOptions:
    """
    This class contains options governing the behavior of the
    [apply_environment_arguments
    ](./#decorative_secrets.environment.apply_environment_arguments) decorator.

    Attributes:
        env: If provided, this dictionary of environment variables will be
            used in lieu of `os.environ` when retrieving environment variable
            values.
    """

    env: Mapping[str, str] = field(default_factory=lambda: os.environ)


def _get_args_options(
    *args: Any,
) -> tuple[tuple[Any, ...], ApplyEnvironmentArgumentsOptions]:
    """
    This function extracts an `ApplyEnvironmentArgumentsOptions` instance
    from the provided arguments, if one is present.
    """
    index: int
    value: Any
    for index, value in enumerate(args):
        if isinstance(value, ApplyEnvironmentArgumentsOptions):
            return (*args[:index], *args[index + 1 :]), value
    return args, ApplyEnvironmentArgumentsOptions()


def apply_environment_arguments(
    *args: ApplyEnvironmentArgumentsOptions,
    **kwargs: str,
) -> Callable:
    """
    This decorator maps parameter names to environment variables.
    Each key represents the name of a parameter in the decorated function
    which accepts an explicit input, and the corresponding mapped value is a
    parameter name accepting an environment variable from which to obtain
    the value when no value is explicitly provided.

    Parameters:
        *args: An optional [ApplyEnvironmentArgumentsOptions
            ](./#decorative_secrets.environment.ApplyEnvironmentArgumentsOptions)
            instance governing the behavior of this decorator. If not provided,
            a default instance of [ApplyEnvironmentArgumentsOptions()
            ](./#decorative_secrets.environment.ApplyEnvironmentArgumentsOptions).
            If multiple instances are provided, only the first will be used.
        **kwargs:
            A mapping of static parameter names to the parameter names
            of arguments accepting environment variable names from which to
            retrieve the value when the key argument is not explicitly
            provided.

    Example:
        ```python
        from functools import (
            cache,
        )
        from decorative_secrets.environment import (
            apply_environment_arguments,
        )
        from my_client_sdk import (
            Client,
        )


        @cache
        @apply_onepassword_arguments(
            client_id="client_id_environment_variable",
            client_secret="client_secret_environment_variable",
        )
        def get_client(
            client_id: str | None = None,
            client_secret: str = None,
            client_id_environment_variable: str | None = None,
            client_secret_environment_variable: str | None = None,
        ) -> Client:
            return Client(
                oauth2_client_id=client_id,
                oauth2_client_secret=client_secret,
            )


        client: Client = get_client(
            client_id_environment_variable=("CLIENT_ID",),
            client_secret_environment_variable=("CLIENT_SECRET",),
        )
        ```
    """
    options: ApplyEnvironmentArgumentsOptions
    _, options = _get_args_options(*args)
    return apply_callback_arguments(
        partial(_getenv, options.env),
        partial(_async_getenv, options.env),
        **kwargs,
    )
