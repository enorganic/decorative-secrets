import os

from decorative_secrets.environment import apply_environment_arguments
from decorative_secrets.onepassword import read_onepassword_secret


def test_apply_environment_arguments(onepassword_vault: str) -> None:
    env: dict[str, str] = os.environ.copy()
    try:
        os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = read_onepassword_secret(
            f"op://{onepassword_vault}/sb466kar2ifqheowaprjqvwn7y/"
            "credential"
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
