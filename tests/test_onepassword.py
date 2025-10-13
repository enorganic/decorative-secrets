import asyncio
import os

from decorative_secrets.environment import apply_environment_arguments
from decorative_secrets.errors import ArgumentsResolutionError
from decorative_secrets.onepassword import (
    _parse_resource,
    _resolve_auth_arguments,
    apply_onepassword_arguments,
    async_read_onepassword_secret,
    read_onepassword_secret,
)


def test_async_read_onepassword_secret(onepassword_vault: str) -> None:
    """
    Verify that the async_read_onepassword_secret function works as intended.
    """
    assert asyncio.run(
        async_read_onepassword_secret(
            f"op://{onepassword_vault}/Databricks Client/hostname"
        )
    )


def test_read_onepassword_secret(onepassword_vault: str) -> None:
    """
    Verify that the async_read_onepassword_secret function works as intended.
    """
    assert read_onepassword_secret(
        f"op://{onepassword_vault}/Databricks Client/hostname"
    )


def test_apply_onepassword_arguments(onepassword_vault: str) -> None:
    """
    Verify that the apply_onepassword_arguments decorator works as intended.
    """

    @apply_onepassword_arguments(
        databricks_host="databricks_host_onepassword",
        databricks_client_id="databricks_client_id_onepassword",
        databricks_client_secret=("databricks_client_secret_onepassword"),
    )
    @apply_environment_arguments(
        databricks_host="databricks_host_environment_variable",
        databricks_client_id="databricks_client_id_environment_variable",
        databricks_client_secret="databricks_client_secret_environment_variable",
    )
    def infer_databricks_credentials(
        databricks_host: str,
        databricks_client_id: str,
        databricks_client_secret: str,
        databricks_host_onepassword: str | None = None,  # noqa: ARG001
        databricks_client_id_onepassword: str | None = None,  # noqa: ARG001
        databricks_client_secret_onepassword: str | None = None,  # noqa: ARG001
        databricks_host_environment_variable: str | None = None,  # noqa: ARG001
        databricks_client_id_environment_variable: str | None = None,  # noqa: ARG001
        databricks_client_secret_environment_variable: str | None = None,  # noqa: ARG001
    ) -> dict[str, str]:
        return {
            "databricks_host": databricks_host,
            "databricks_client_id": databricks_client_id,
            "databricks_client_secret": databricks_client_secret,
        }

    credentials: dict[str, str] = infer_databricks_credentials(
        databricks_host_onepassword=(
            f"op://{onepassword_vault}/Databricks Client/hostname"
        ),
        databricks_client_id_onepassword=(
            f"op://{onepassword_vault}/Databricks Client/username"
        ),
        databricks_client_secret_onepassword=(
            f"op://{onepassword_vault}/Databricks Client/credential"
        ),
    )

    env: dict[str, str] = os.environ.copy()
    try:
        # Test the same operation using a service account token
        token: str = read_onepassword_secret(
            f"op://{onepassword_vault}/62u4plbr2i7ueb4boywtbbyd24/credential"
        )
        os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = token
        assert (
            infer_databricks_credentials(
                databricks_host_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/hostname"
                ),
                databricks_client_id_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/username"
                ),
                databricks_client_secret_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/credential"
                ),
            )
            == credentials
        )
        # Ensure that setting an environment variable does not change
        # the result
        os.environ["DATABRICKS_HOST"] = "https://nonsense.cloud.databricks.com"
        assert (
            infer_databricks_credentials(
                databricks_host_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/hostname"
                ),
                databricks_client_id_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/username"
                ),
                databricks_client_secret_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/credential"
                ),
                databricks_host_environment_variable="DATABRICKS_HOST",
            )
            == credentials
        )
        # ...unless the preceding lookup is missing
        assert (
            infer_databricks_credentials(
                databricks_host_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/nonsense"
                ),
                databricks_client_id_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/username"
                ),
                databricks_client_secret_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/credential"
                ),
                databricks_host_environment_variable="DATABRICKS_HOST",
            )
            != credentials
        )
        # Make sure an error is raised if no lookups are successful for
        # a required parameter
        try:
            infer_databricks_credentials(
                databricks_host_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/nonsense"
                ),
                databricks_client_id_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/username"
                ),
                databricks_client_secret_onepassword=(
                    f"op://{onepassword_vault}/Databricks Client/credential"
                ),
                databricks_host_environment_variable="nonsense",
            )
        except ArgumentsResolutionError:
            pass
        else:
            message: str = "Expected an `ArgumentsResolutionError`"
            raise AssertionError(message)
    finally:
        os.environ.clear()
        os.environ.update(env)


def test_resolve_auth_arguments() -> None:
    """
    Test auth argument resolution.
    """
    # Retain an original copy of environment variables
    env: dict[str, str] = os.environ.copy()
    os.environ.clear()
    try:
        os.environ.update(
            {
                "OP_ACCOUNT": "nonsense.1password.com",
                "OP_CONNECT_HOST": "https://1password.nonsense.com",
                "OP_CONNECT_TOKEN": "CONNECT-1234",
                "OP_SERVICE_ACCOUNT_TOKEN": "1234",
            }
        )
        assert _resolve_auth_arguments() == (
            "nonsense.1password.com",
            "CONNECT-1234",
            "https://1password.nonsense.com",
        )
        os.environ.pop("OP_CONNECT_HOST")
        assert _resolve_auth_arguments() == (
            "nonsense.1password.com",
            "1234",
            None,
        )
        assert _resolve_auth_arguments(
            host="https://1password.nonsense.com"
        ) == (
            "nonsense.1password.com",
            "CONNECT-1234",
            "https://1password.nonsense.com",
        )
        os.environ.clear()
        assert _resolve_auth_arguments(
            account="nonsense.1password.com",
            token="CONNECT-1234",
            host="https://1password.nonsense.com",
        ) == (
            "nonsense.1password.com",
            "CONNECT-1234",
            "https://1password.nonsense.com",
        )
    finally:
        # Restore original environment variables
        os.environ.clear()
        os.environ.update(env)


def test_parse_resource() -> None:
    """
    Test resource parsing.
    """
    assert _parse_resource("op://My Vault/My Item/fieldname") == (
        "My Vault",
        "My Item",
        "fieldname",
    )
