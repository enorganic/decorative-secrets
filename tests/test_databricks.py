import os
import sys
from subprocess import check_call
from typing import TYPE_CHECKING

from databricks.sdk.errors.platform import ResourceDoesNotExist
from onepassword.errors import (  # type: ignore[import-untyped]
    RateLimitExceededException,
)

from decorative_secrets._utilities import get_exception_text
from decorative_secrets.databricks import (
    _install_databricks_cli,
    _install_sh_databricks_cli,
    apply_databricks_secrets_arguments,
    get_secret,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def test_install_sh_databricks_cli() -> None:
    """
    Verify that the Databricks CLI install script can be downloaded and run.
    """
    _install_sh_databricks_cli()


def test_install_databricks_cli() -> None:
    """
    Verify that the Databricks CLI install script can be downloaded and run.
    """
    _install_databricks_cli()


def test_get_secret(databricks_env: dict[str, str]) -> None:
    env: Mapping[str, str] = os.environ.copy()
    if not os.getenv("CI"):
        # If not running unsupervised, test interactive login
        assert os.getenv("DATABRICKS_HOST")
        os.environ.pop("DATABRICKS_CLIENT_ID", None)
        os.environ.pop("DATABRICKS_CLIENT_SECRET", None)
        try:
            assert (
                get_secret("decorative-secrets-test", "my-secret-key")
                == "my-secret-value"
            )
        except RateLimitExceededException:
            # TODO: Remove this pending approval of
            # [this](https://github.com/1Password/for-open-source/issues/1337)
            pass
        except Exception:
            # TODO: Remove this pending approval of
            # [this](https://github.com/1Password/for-open-source/issues/1337)
            if not (
                "rate limit exceeded" in get_exception_text()
                and os.getenv("CI")
            ):
                raise
    try:
        os.environ.update(databricks_env)
        assert (
            get_secret("decorative-secrets-test", "my-secret-key")
            == "my-secret-value"
        )
        try:
            get_secret("decorative-secrets-test", "my-fake-secret-key")
        except ResourceDoesNotExist:
            pass
        else:
            message: str = "Expected `ResourceDoesNotExist`"
            raise AssertionError(message)
    finally:
        os.environ.clear()
        os.environ.update(env)


def test_apply_databricks_secret_arguments(
    databricks_env: dict[str, str],
) -> None:
    env: Mapping[str, str] = os.environ.copy()

    @apply_databricks_secrets_arguments(
        my_secret="my_secret_databricks_secret",
    )
    def get_my_secret(
        my_secret: str,
        my_secret_databricks_secret: str | None = None,  # noqa: ARG001
    ) -> str:
        return my_secret

    try:
        os.environ.update(databricks_env)
        assert (
            get_my_secret(
                my_secret_databricks_secret=(
                    "decorative-secrets-test",
                    "my-secret-key",
                )
            )
            == "my-secret-value"
        )
    finally:
        os.environ.clear()
        os.environ.update(env)


if __name__ == "__main__":
    check_call([sys.executable, "-m", "pytest", "-s", "-vv", __file__])
