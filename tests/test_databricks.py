import os
import sys
from typing import TYPE_CHECKING

import pytest
from databricks.sdk.errors.platform import ResourceDoesNotExist
from pyspark import cloudpickle

from decorative_secrets.databricks import (
    _databricks_auth_describe,
    _databricks_auth_profiles,
    _get_host_profile,
    _install_databricks_cli,
    _install_sh_databricks_cli,
    apply_databricks_secrets_arguments,
    databricks_auth_login,
    get_databricks_secret,
    get_databricks_workspace_client,
    get_dbutils,
    which_databricks,
)
from decorative_secrets.databricks import (
    main as databricks_main,
)
from decorative_secrets.subprocess import check_output

if TYPE_CHECKING:
    from collections.abc import Mapping

    from databricks.sdk import WorkspaceClient
    from databricks.sdk.dbutils import RemoteDbUtils
    from databricks.sdk.service.iam import User

    from decorative_secrets.databricks import _DatabricksAuthProfile


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
                get_databricks_secret(
                    "decorative-secrets-test", "my-secret-key"
                )
                == "my-secret-value"
            )
        finally:
            os.environ.clear()
            os.environ.update(env)
    try:
        os.environ.update(databricks_env)
        assert (
            get_databricks_secret("decorative-secrets-test", "my-secret-key")
            == "my-secret-value"
        )
        try:
            get_databricks_secret(
                "decorative-secrets-test", "my-fake-secret-key"
            )
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


def test_pickle_workspace_client() -> None:
    client: WorkspaceClient = get_databricks_workspace_client()
    me: User = client.current_user.me()
    pickled_client: bytes = cloudpickle.dumps(client)
    unpickled_client: WorkspaceClient = cloudpickle.loads(pickled_client)
    assert unpickled_client.current_user.me() == me


def test_get_dbutils_returns_real_client_dbutils() -> None:
    """
    `get_dbutils` builds a working `dbutils` from a real workspace client
    when not running inside a notebook/IPython environment.
    """
    dbutils: RemoteDbUtils = get_dbutils()
    assert (
        dbutils.secrets.get("decorative-secrets-test", "my-secret-key")
        == "my-secret-value"
    )


def test_which_databricks() -> None:
    """
    `which_databricks` locates a working `databricks` executable.
    """
    databricks: str = which_databricks()
    assert check_output((databricks, "--version"))


def test_databricks_auth_profiles() -> None:
    """
    `_databricks_auth_profiles` parses real `databricks auth profiles`
    output into the documented shape and includes at least one profile.
    """
    profiles: list[_DatabricksAuthProfile] = _databricks_auth_profiles()[
        "profiles"
    ]
    assert profiles
    assert all(
        ("name" in profile) and ("host" in profile) for profile in profiles
    )


def test_get_host_profile() -> None:
    """
    A configured profile's host resolves back to its profile name.
    """
    profile: _DatabricksAuthProfile = _databricks_auth_profiles()[
        "profiles"
    ][0]
    assert _get_host_profile(profile["host"]) == profile["name"]


def test_databricks_auth_describe() -> None:
    """
    `_databricks_auth_describe` reports success for the already
    authenticated local profile.
    """
    profile: _DatabricksAuthProfile = next(
        profile
        for profile in _databricks_auth_profiles()["profiles"]
        if profile.get("valid")
    )
    assert (
        _databricks_auth_describe(profile=profile["name"]).get("status")
        == "success"
    )


def test_databricks_auth_login_skips_when_already_authenticated() -> None:
    """
    With `force=False` (the default), an already-authenticated profile
    short-circuits rather than attempting a fresh login.
    """
    profile: _DatabricksAuthProfile = next(
        profile
        for profile in _databricks_auth_profiles()["profiles"]
        if profile.get("valid")
    )
    databricks_auth_login(profile=profile["name"])


def test_databricks_auth_login_env_fallback() -> None:
    """
    With no explicit `host`/`profile`/`target`, `DATABRICKS_HOST` is
    honored when resolving whether a login is already valid.
    """
    profile: _DatabricksAuthProfile = next(
        profile
        for profile in _databricks_auth_profiles()["profiles"]
        if profile.get("valid")
    )
    env: dict[str, str] = os.environ.copy()
    try:
        os.environ["DATABRICKS_HOST"] = profile["host"]
        os.environ.pop("DATABRICKS_CONFIG_PROFILE", None)
        databricks_auth_login()
    finally:
        os.environ.clear()
        os.environ.update(env)


@pytest.mark.skipif(
    bool(os.getenv("CI")),
    reason=(
        "Forcing a real login requires an interactive OAuth browser flow, "
        "so this can only be run supervised, outside CI."
    ),
)
def test_databricks_auth_login_force_reauthenticates() -> None:
    """
    `force=True` triggers a real second CLI login round-trip rather than
    returning the memoized result from `_databricks_auth_login`'s `@cache`.
    """
    profile: _DatabricksAuthProfile = next(
        profile
        for profile in _databricks_auth_profiles()["profiles"]
        if profile.get("valid")
    )
    databricks_auth_login(profile=profile["name"])
    databricks_auth_login(profile=profile["name"], force=True)
    assert (
        _databricks_auth_describe(profile=profile["name"]).get("status")
        == "success"
    )


@pytest.mark.skipif(
    bool(os.getenv("CI")),
    reason=(
        "Forcing a real login requires an interactive OAuth browser flow, "
        "so this can only be run supervised, outside CI."
    ),
)
def test_databricks_auth_login_force_clears_cache_for_other_profiles() -> (
    None
):
    """
    `_databricks_auth_login.cache_clear()` wipes the entire cache, not just
    the entry for the forced profile. Confirm an unrelated cached profile
    still authenticates afterward (transparently re-running, rather than
    erroring) instead of being left corrupted.
    """
    valid_profiles: list[_DatabricksAuthProfile] = [
        profile
        for profile in _databricks_auth_profiles()["profiles"]
        if profile.get("valid")
    ]
    if len(valid_profiles) < 2:
        pytest.skip(
            "Requires at least two valid, already-authenticated Databricks "
            "CLI profiles configured locally."
        )
    first: _DatabricksAuthProfile = valid_profiles[0]
    second: _DatabricksAuthProfile = valid_profiles[1]
    databricks_auth_login(profile=first["name"])
    databricks_auth_login(profile=second["name"])
    databricks_auth_login(profile=first["name"], force=True)
    assert (
        _databricks_auth_describe(profile=second["name"]).get("status")
        == "success"
    )


def test_databricks_cli_get_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    The `get` CLI subcommand prints the same value as calling
    `get_databricks_secret` directly.
    """
    argv: list[str] = sys.argv
    try:
        sys.argv = [
            "decorative-secrets-databricks",
            "get",
            "decorative-secrets-test",
            "my-secret-key",
        ]
        databricks_main()
    finally:
        sys.argv = argv
    assert capsys.readouterr().out.strip() == get_databricks_secret(
        "decorative-secrets-test", "my-secret-key"
    )


def test_databricks_cli_install_command() -> None:
    """
    The `install` CLI subcommand installs the Databricks CLI (idempotent
    when it's already installed).
    """
    argv: list[str] = sys.argv
    try:
        sys.argv = ["decorative-secrets-databricks", "install"]
        databricks_main()
    finally:
        sys.argv = argv


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
