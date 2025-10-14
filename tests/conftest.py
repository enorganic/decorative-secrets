import os

import pytest

from decorative_secrets.onepassword import read_onepassword_secret

DEFAULT_OP_VAULT: str = "decorative-secrets-test"


@pytest.fixture(name="onepassword_vault", scope="session")
def get_onepassword_vault() -> str:
    """
    Set up the environment variables for testing.
    """
    return os.getenv("OP_VAULT", DEFAULT_OP_VAULT)


@pytest.fixture(name="databricks_env", scope="session")
def get_databricks_env(onepassword_vault: str) -> dict[str, str]:
    """
    Get Databricks environment variables for testing.
    """
    return {
        "DATABRICKS_HOST": os.getenv(
            "DATABRICKS_HOST",
            read_onepassword_secret(
                f"op://{onepassword_vault}/Databricks Client/hostname",
                account="my.1password.com",
            ),
        ),
        "DATABRICKS_CLIENT_ID": os.getenv(
            "DATABRICKS_CLIENT_ID",
            read_onepassword_secret(
                f"op://{onepassword_vault}/Databricks Client/username",
                account="my.1password.com",
            ),
        ),
        "DATABRICKS_CLIENT_SECRET": os.getenv(
            "DATABRICKS_CLIENT_SECRET",
            read_onepassword_secret(
                f"op://{onepassword_vault}/Databricks Client/credential",
                account="my.1password.com",
            ),
        ),
    }
