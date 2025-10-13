from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import TYPE_CHECKING

from decorative_secrets._utilities import apply_callback_arguments

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping


async def _async_getenv(env: Mapping[str, str], name: str) -> str | None:
    return await asyncio.to_thread(env.__getitem__, name)


def _getenv(env: Mapping[str, str], name: str) -> str | None:
    return env[name]


def apply_environment_arguments(
    environment_arguments: (
        Mapping[str, str] | Iterable[tuple[str, str]]
    ) = (),
    env: dict[str, str] | None = None,
    **kwargs: str,
) -> Callable:
    """
    This decorator maps parameter names to environment variables.
    Each key represents the name of a parameter in the decorated function
    which accepts an explicit input, and the corresponding mapped value is a
    parameter name accepting an environment variable from which to obtain
    the value when no value is explicitly provided.

    Parameters:
        environment_arguments:
            A mapping of static parameter names to the parameter names
            of arguments accepting environment variable names from which to
            retrieve the value when the key argument is not explicitly
            provided.
        env: An (optional) dictionary of environment variable names to values
            to use in lieu of `os.environ`.
        kwargs: Parameter name mappings may also be provided as keyword
            arguments instead of passing a dictionary to
            `environment_arguments`.

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
    return apply_callback_arguments(
        partial(_getenv, env or os.environ),
        partial(_async_getenv, env or os.environ),
        environment_arguments,
        **kwargs,
    )
