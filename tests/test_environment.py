import asyncio
import os

import pytest

from decorative_secrets.environment import (
    ApplyEnvironmentArgumentsOptions,
    _async_getenv,
    apply_environment_arguments,
)
from decorative_secrets.onepassword import read_onepassword_secret


def test_apply_environment_arguments(onepassword_vault: str) -> None:
    env: dict[str, str] = os.environ.copy()
    try:
        os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = read_onepassword_secret(
            f"op://{onepassword_vault}/62u4plbr2i7ueb4boywtbbyd24/credential",
            account="enorganic.1password.com",
        )

        @apply_environment_arguments(token="token_environment_variable")
        def get_token(
            token: str | None = None,
            token_environment_variable: str | None = None,  # noqa: ARG001
        ) -> str | None:
            return token

        assert get_token(
            token_environment_variable="OP_SERVICE_ACCOUNT_TOKEN"
        ) == get_token(token=os.getenv("OP_SERVICE_ACCOUNT_TOKEN"))
    finally:
        os.environ.clear()
        os.environ.update(env)


def test_apply_environment_arguments_with_options_env() -> None:
    """
    A positional `ApplyEnvironmentArgumentsOptions` instance is extracted
    from the decorator arguments, and its `env` mapping is used in lieu of
    `os.environ` when resolving values.
    """
    options = ApplyEnvironmentArgumentsOptions(env={"MY_TOKEN": "secret"})

    @apply_environment_arguments(options, token="token_environment_variable")
    def get_token(
        token: str | None = None,
        token_environment_variable: str | None = None,  # noqa: ARG001
    ) -> str | None:
        return token

    assert get_token(token_environment_variable="MY_TOKEN") == "secret"


def test_async_getenv() -> None:
    """
    `_async_getenv` reads a value from the provided mapping off-thread.
    """
    assert asyncio.run(_async_getenv({"MY_TOKEN": "secret"}, "MY_TOKEN")) == (
        "secret"
    )


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
