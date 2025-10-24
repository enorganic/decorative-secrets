import os

import pytest
from onepassword.errors import (  # type: ignore[import-untyped]
    RateLimitExceededException,
)

from decorative_secrets._utilities import get_exception_text
from decorative_secrets.environment import apply_environment_arguments
from decorative_secrets.onepassword import read_onepassword_secret


def test_apply_environment_arguments(onepassword_vault: str) -> None:
    env: dict[str, str] = os.environ.copy()
    try:
        os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = read_onepassword_secret(
            f"op://{onepassword_vault}/62u4plbr2i7ueb4boywtbbyd24/"
            "credential",
            account="my.1password.com",
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
    except RateLimitExceededException:
        # TODO: Remove this pending approval of
        # [this](https://github.com/1Password/for-open-source/issues/1337)
        pass
    except Exception:
        # TODO: Remove this pending approval of
        # [this](https://github.com/1Password/for-open-source/issues/1337)
        if not (
            "rate limit exceeded" in get_exception_text() and os.getenv("CI")
        ):
            raise
    finally:
        os.environ.clear()
        os.environ.update(env)


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
