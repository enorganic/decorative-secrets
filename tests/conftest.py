import os

import pytest

DEFAULT_OP_VAULT: str = "decorative-secrets-test"


@pytest.fixture(name="onepassword_vault", scope="session")
def get_onepassword_vault() -> str:
    """
    Set up the environment variables for testing.
    """
    return os.getenv("OP_VAULT", DEFAULT_OP_VAULT)
