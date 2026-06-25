import os

import pytest

from decorative_secrets import utilities
from decorative_secrets.onepassword import read_onepassword_secret

DEFAULT_OP_VAULT: str = "decorative-secrets-test"


@pytest.fixture(name="onepassword_vault", scope="session")
def get_onepassword_vault() -> str:
    """
    Set up the environment variables for testing.
    """
    return os.getenv("OP_VAULT", DEFAULT_OP_VAULT)


@pytest.fixture(name="databricks_env", scope="session")
def get_databricks_env(onepassword_vault: str) -> dict[str, str | None]:
    """
    Get Databricks environment variables for testing.
    """
    if os.getenv("CI"):
        return {
            "DATABRICKS_HOST": os.getenv("DATABRICKS_HOST"),
            "DATABRICKS_CLIENT_ID": os.getenv("DATABRICKS_CLIENT_ID"),
            "DATABRICKS_CLIENT_SECRET": os.getenv("DATABRICKS_CLIENT_SECRET"),
        }
    return {
        "DATABRICKS_HOST": read_onepassword_secret(
            f"op://{onepassword_vault}/Databricks Client/hostname",
            account="my.1password.com",
        ),
        "DATABRICKS_CLIENT_ID": read_onepassword_secret(
            f"op://{onepassword_vault}/Databricks Client/username",
            account="my.1password.com",
        ),
        "DATABRICKS_CLIENT_SECRET": read_onepassword_secret(
            f"op://{onepassword_vault}/Databricks Client/credential",
            account="my.1password.com",
        ),
    }


@pytest.fixture
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Replace the blocking backoff sleeps used by `retry` with no-ops so
    retry behavior can be tested without waiting for exponential backoff.
    """

    async def _async_sleep(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(utilities, "sleep", lambda *_, **__: None)
    monkeypatch.setattr(utilities.asyncio, "sleep", _async_sleep)
