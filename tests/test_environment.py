import os
from decorative_secrets.environment import apply_environment_arguments


def test_apply_environment_arguments() -> None:
    apply_environment_arguments(
        token="OP_SERVICE_ACCOUNT_TOKEN"
    )
    def get_token(
        token: str | None = None,
        token_environment_variable: str | None = None,
    ) -> str | None:
        return token
    
    assert get_token(
        token_environment_variable="OP_SERVICE_ACCOUNT_TOKEN"
    ) == get_token(
        token=os.getenv("OP_SERVICE_ACCOUNT_TOKEN")
    )