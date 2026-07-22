import asyncio
import os
import sys
from contextlib import suppress
from subprocess import TimeoutExpired

import pytest

from decorative_secrets.environment import apply_environment_arguments
from decorative_secrets.errors import (
    ArgumentsResolutionError,
    OnePasswordCommandLineInterfaceNotInstalledError,
)
from decorative_secrets.onepassword import (
    ApplyOnepasswordArgumentsOptions,
    _install_op,
    _op_signin,
    _parse_resource,
    _read_onepassword_secret,
    _resolve_auth_arguments,
    apply_onepassword_arguments,
    async_read_onepassword_secret,
    iter_op_account_list,
    op_signin,
    read_onepassword_secret,
    which_op,
)
from decorative_secrets.onepassword import (
    main as onepassword_main,
)
from decorative_secrets.subprocess import check_output
from decorative_secrets.utilities import get_exception_text


def test_which_op() -> None:
    """
    Verify that the 1Password CLI is installed on invocation.
    """
    try:
        op: str = which_op()
        assert check_output((op, "--version"))
    except OnePasswordCommandLineInterfaceNotInstalledError:
        # The 1Password CLI should be possible to bootstrap on macOS and
        # Windows, but not Linux
        if sys.platform.startswith(("darwin", "win32")):
            raise


def test_which_op_timeout_expires() -> None:
    """
    A near-zero `timeout` causes `which_op` to raise `TimeoutExpired`.
    """
    with pytest.raises(TimeoutExpired):
        which_op(timeout=1e-6)


def test_install_op() -> None:
    """
    Verify that the 1Password CLI can be installed.
    """
    with suppress(OnePasswordCommandLineInterfaceNotInstalledError):
        _install_op()
        op: str = which_op()
        assert check_output((op, "--version"))


def _require_op_accounts() -> list[str]:
    """
    Return the interactively-registered 1Password account(s) (from
    `op account list`), or skip if there are none. A service-account-token
    -only environment (e.g. this project's CI, which only sets
    `OP_SERVICE_ACCOUNT_TOKEN`) never registers an account this way, so
    `iter_op_account_list()` legitimately yields nothing there.
    """
    accounts: list[str] = list(iter_op_account_list())
    if not accounts:
        pytest.skip(
            "Requires at least one interactively signed-in 1Password "
            "account configured locally."
        )
    return accounts


def test_iter_op_account_list() -> None:
    """
    `iter_op_account_list` yields the real configured 1Password account(s).
    """
    assert _require_op_accounts()


def test_iter_op_account_list_timeout_expires() -> None:
    """
    A near-zero `timeout` causes `iter_op_account_list` to raise
    `TimeoutExpired`.
    """
    _require_op_accounts()
    with pytest.raises(TimeoutExpired):
        list(iter_op_account_list(timeout=1e-6))


def test_op_signin_timeout_expires() -> None:
    """
    A near-zero `timeout` causes `op_signin` to raise `TimeoutExpired`.
    """
    account: str = _require_op_accounts()[0]
    with pytest.raises(TimeoutExpired):
        op_signin(account, timeout=1e-6)


def test_op_signin_timeout_cache_key() -> None:
    """
    Distinct `timeout` values are distinct `_op_signin` cache keys: each
    triggers its own real CLI round-trip (a cache miss), while repeating
    the same `timeout` hits cache.
    """
    account: str = _require_op_accounts()[0]
    _op_signin.cache_clear()
    _op_signin(account, timeout=None)
    misses_after_first: int = _op_signin.cache_info().misses
    _op_signin(account, timeout=30)
    misses_after_second: int = _op_signin.cache_info().misses
    assert misses_after_second == misses_after_first + 1
    _op_signin(account, timeout=30)
    assert _op_signin.cache_info().misses == misses_after_second


def test_op_signin_no_account_iterates_all_accounts() -> None:
    """
    With no explicit account and `OP_ACCOUNT` unset, `op_signin` signs in
    to at least one real account and returns a usable `op` path. `--version`
    doesn't require being signed in at all, so this checks `op vault list`
    for each known account instead, since that command fails without a
    valid session.
    """
    accounts: list[str] = _require_op_accounts()
    env: dict[str, str] = os.environ.copy()
    try:
        os.environ.pop("OP_ACCOUNT", None)
        op: str = op_signin()
        account: str
        for account in accounts:
            check_output((op, "vault", "list", "--account", account))
    finally:
        os.environ.clear()
        os.environ.update(env)


def test_op_signin_with_explicit_account() -> None:
    """
    Passing an explicit account signs in to that account specifically.
    `--version` doesn't require being signed in at all, so this checks
    `op vault list` for that account instead, since that command fails
    without a valid session.
    """
    account: str = _require_op_accounts()[0]
    op: str = op_signin(account)
    check_output((op, "vault", "list", "--account", account))


def test_async_read_onepassword_secret(onepassword_vault: str) -> None:
    """
    Verify that the async_read_onepassword_secret function works as intended.
    """
    assert asyncio.run(
        async_read_onepassword_secret(
            f"op://{onepassword_vault}/Databricks Client/hostname",
            account="enorganic.1password.com",
        )
    )


def test_async_read_onepassword_secret_via_sdk_token(
    onepassword_vault: str,
) -> None:
    """
    With a service-account `token` passed and no `host`,
    `async_read_onepassword_secret` resolves the secret via the
    `onepassword-sdk` client rather than the CLI.
    """
    token: str = read_onepassword_secret(
        f"op://{onepassword_vault}/t4s43shaaab22aj36nmw56royy/credential",
        account="enorganic.1password.com",
    )
    assert asyncio.run(
        async_read_onepassword_secret(
            f"op://{onepassword_vault}/Databricks Client/hostname",
            token=token,
        )
    )


def test_read_onepassword_secret(onepassword_vault: str) -> None:
    """
    Verify that the async_read_onepassword_secret function works as intended.
    """
    assert read_onepassword_secret(
        f"op://{onepassword_vault}/Databricks Client/hostname",
        account="enorganic.1password.com",
    )


def test_read_onepassword_secret_timeout_expires(
    onepassword_vault: str,
) -> None:
    """
    A near-zero `timeout` causes `read_onepassword_secret` to raise
    `TimeoutExpired` when resolving via the CLI.
    """
    with pytest.raises(TimeoutExpired):
        read_onepassword_secret(
            f"op://{onepassword_vault}/Databricks Client/hostname",
            account="enorganic.1password.com",
            timeout=1e-6,
        )


def test_async_read_onepassword_secret_timeout_expires(
    onepassword_vault: str,
) -> None:
    """
    A near-zero `timeout` causes `async_read_onepassword_secret` to raise
    `TimeoutExpired` when resolving via the CLI.
    """
    with pytest.raises(TimeoutExpired):
        asyncio.run(
            async_read_onepassword_secret(
                f"op://{onepassword_vault}/Databricks Client/hostname",
                account="enorganic.1password.com",
                timeout=1e-6,
            )
        )


def test_read_onepassword_secret_ignores_unrelated_env_changes(
    onepassword_vault: str,
) -> None:
    """
    Changing an environment variable unrelated to 1Password does not bust
    `read_onepassword_secret`'s cache, while changing an `OP_`-prefixed
    variable does.
    """
    resource: str = f"op://{onepassword_vault}/Databricks Client/hostname"
    env: dict[str, str] = os.environ.copy()
    try:
        _read_onepassword_secret.cache_clear()
        read_onepassword_secret(resource, account="enorganic.1password.com")
        misses_after_first: int = _read_onepassword_secret.cache_info().misses
        os.environ["DECORATIVE_SECRETS_TEST_UNRELATED"] = "1"
        read_onepassword_secret(resource, account="enorganic.1password.com")
        assert _read_onepassword_secret.cache_info().misses == (
            misses_after_first
        )
        os.environ["OP_TEST_UNRELATED"] = "2"
        read_onepassword_secret(resource, account="enorganic.1password.com")
        assert _read_onepassword_secret.cache_info().misses == (
            misses_after_first + 1
        )
    finally:
        os.environ.clear()
        os.environ.update(env)


def test_apply_onepassword_arguments_timeout_expires(
    onepassword_vault: str,
) -> None:
    """
    A `timeout` set on `ApplyOnepasswordArgumentsOptions` reaches the
    underlying secret lookup, surfacing as an `ArgumentsResolutionError`
    (wrapping the `TimeoutExpired`) the same way other callback failures
    propagate through `apply_callback_arguments`.
    """

    @apply_onepassword_arguments(
        ApplyOnepasswordArgumentsOptions(
            account="enorganic.1password.com", timeout=1e-6
        ),
        my_secret="my_secret_onepassword",
    )
    def get_my_secret(
        my_secret: str,
        my_secret_onepassword: str | None = None,  # noqa: ARG001
    ) -> str:
        return my_secret

    with pytest.raises(ArgumentsResolutionError):
        get_my_secret(
            my_secret_onepassword=(
                f"op://{onepassword_vault}/Databricks Client/hostname"
            )
        )


def test_apply_onepassword_arguments(onepassword_vault: str) -> None:
    """
    Verify that the apply_onepassword_arguments decorator works as intended.
    """

    @apply_onepassword_arguments(
        onepassword_account="enorganic.1password.com",
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

    env: dict[str, str] = os.environ.copy()
    try:
        credentials: dict[str, str] = infer_databricks_credentials(
            databricks_host_onepassword=(
                f"op://{onepassword_vault}/Databricks Client/hostname",
            ),
            databricks_client_id_onepassword=(
                f"op://{onepassword_vault}/Databricks Client/username",
            ),
            databricks_client_secret_onepassword=(
                f"op://{onepassword_vault}/Databricks Client/credential",
            ),
        )
        # Test the same operation using a service account token
        os.environ.setdefault(
            "OP_SERVICE_ACCOUNT_TOKEN",
            read_onepassword_secret(
                f"op://{onepassword_vault}/"
                "t4s43shaaab22aj36nmw56royy/credential"
            ),
        )
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
    except ArgumentsResolutionError:
        if "rate limit exceeded" in get_exception_text() and os.getenv("CI"):
            # TODO: Remove this pending approval of
            # [this](https://github.com/1Password/for-open-source/issues/1337)
            pass
    finally:
        os.environ.clear()
        os.environ.update(env)


def test_onepassword_cli_get_command(
    capsys: pytest.CaptureFixture[str],
    onepassword_vault: str,
) -> None:
    """
    The `get` CLI subcommand prints the same value as calling
    `read_onepassword_secret` directly.
    """
    reference: str = f"op://{onepassword_vault}/Databricks Client/hostname"
    argv: list[str] = sys.argv
    try:
        sys.argv = [
            "decorative-secrets-onepassword",
            "get",
            reference,
            "--account",
            "enorganic.1password.com",
        ]
        onepassword_main()
    finally:
        sys.argv = argv
    assert capsys.readouterr().out.strip() == read_onepassword_secret(
        reference, account="enorganic.1password.com"
    )


def test_onepassword_cli_install_command() -> None:
    """
    The `install` CLI subcommand installs the 1Password CLI (idempotent
    when it's already installed).
    """
    argv: list[str] = sys.argv
    try:
        sys.argv = ["decorative-secrets-onepassword", "install"]
        with suppress(OnePasswordCommandLineInterfaceNotInstalledError):
            onepassword_main()
    finally:
        sys.argv = argv


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


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
