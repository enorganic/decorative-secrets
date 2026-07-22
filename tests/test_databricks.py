from __future__ import annotations

import os
import sys
from subprocess import CalledProcessError, TimeoutExpired
from time import monotonic
from typing import TYPE_CHECKING

import pytest
from databricks.sdk.errors.platform import ResourceDoesNotExist
from pyspark import cloudpickle

from decorative_secrets._utilities import get_prefixed_environ
from decorative_secrets.databricks import (
    DatabricksWorkspaceClientArguments,
    _databricks_auth_describe,
    _databricks_auth_login,
    _databricks_auth_profiles,
    _get_env_databricks_workspace_client,
    _get_host_profile,
    _get_secret,
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
from decorative_secrets.errors import ArgumentsResolutionError
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


def test_get_databricks_secret_ignores_unrelated_env_changes(
    databricks_env: dict[str, str],
) -> None:
    """
    Changing an environment variable unrelated to Databricks does not bust
    `get_databricks_secret`'s cache, while changing a `DATABRICKS_`-prefixed
    variable does.
    """
    env: Mapping[str, str] = os.environ.copy()
    try:
        os.environ.update(databricks_env)
        _get_secret.cache_clear()
        get_databricks_secret("decorative-secrets-test", "my-secret-key")
        misses_after_first: int = _get_secret.cache_info().misses
        os.environ["DECORATIVE_SECRETS_TEST_UNRELATED"] = "1"
        get_databricks_secret("decorative-secrets-test", "my-secret-key")
        assert _get_secret.cache_info().misses == misses_after_first
        os.environ["DATABRICKS_TEST_UNRELATED"] = "2"
        get_databricks_secret("decorative-secrets-test", "my-secret-key")
        assert _get_secret.cache_info().misses == misses_after_first + 1
    finally:
        os.environ.clear()
        os.environ.update(env)


def test_get_databricks_secret_timeout_expires() -> None:
    """
    A near-zero `timeout` reaches the implicit CLI-based auth check and
    raises `TimeoutExpired`, when no client credentials are available to
    bypass it entirely.
    """
    profile: _DatabricksAuthProfile = _require_valid_databricks_profile()
    env: Mapping[str, str] = os.environ.copy()
    try:
        os.environ.pop("DATABRICKS_CLIENT_ID", None)
        os.environ.pop("DATABRICKS_CLIENT_SECRET", None)
        _get_secret.cache_clear()
        _get_env_databricks_workspace_client.cache_clear()
        with pytest.raises(TimeoutExpired):
            get_databricks_secret(
                "decorative-secrets-test",
                "my-secret-key",
                profile=profile["name"],
                timeout=1e-6,
            )
    finally:
        os.environ.clear()
        os.environ.update(env)


def test_apply_databricks_secrets_arguments_timeout_expires() -> None:
    """
    A `timeout` set on `DatabricksWorkspaceClientArguments` reaches the
    underlying secret lookup, surfacing as an `ArgumentsResolutionError`
    (wrapping the `TimeoutExpired`) the same way other callback failures
    propagate through `apply_callback_arguments`.
    """
    profile: _DatabricksAuthProfile = _require_valid_databricks_profile()
    env: Mapping[str, str] = os.environ.copy()

    @apply_databricks_secrets_arguments(
        DatabricksWorkspaceClientArguments(
            profile=profile["name"], timeout=1e-6
        ),
        my_secret="my_secret_databricks_secret",
    )
    def get_my_secret(
        my_secret: str,
        my_secret_databricks_secret: str | None = None,  # noqa: ARG001
    ) -> str:
        return my_secret

    try:
        os.environ.pop("DATABRICKS_CLIENT_ID", None)
        os.environ.pop("DATABRICKS_CLIENT_SECRET", None)
        _get_secret.cache_clear()
        _get_env_databricks_workspace_client.cache_clear()
        with pytest.raises(ArgumentsResolutionError):
            get_my_secret(
                my_secret_databricks_secret=(
                    "decorative-secrets-test",
                    "my-secret-key",
                )
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


def test_which_databricks_timeout_expires() -> None:
    """
    A near-zero `timeout` causes `which_databricks` to raise
    `TimeoutExpired`.
    """
    with pytest.raises(TimeoutExpired):
        which_databricks(timeout=1e-6)


def _require_databricks_profiles() -> list[_DatabricksAuthProfile]:
    """
    Return the locally configured Databricks CLI profiles, or skip if none
    exist (e.g. on a CI runner that only authenticates via
    `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` and never runs
    `databricks auth login`, so no profile is ever registered). With no
    `~/.databrickscfg` at all, `databricks auth profiles -o json` exits
    non-zero rather than returning an empty list, so that has to be caught
    too, not just an empty result.
    """
    try:
        profiles: list[_DatabricksAuthProfile] = _databricks_auth_profiles()[
            "profiles"
        ]
    except CalledProcessError:
        profiles = []
    if not profiles:
        pytest.skip(
            "Requires at least one Databricks CLI profile configured "
            "locally (e.g. via `databricks auth login`)."
        )
    return profiles


def _require_valid_databricks_profile() -> _DatabricksAuthProfile:
    """
    Return a valid, already-authenticated local profile, or skip if none
    exists.
    """
    profile: _DatabricksAuthProfile
    for profile in _require_databricks_profiles():
        if profile.get("valid"):
            return profile
    pytest.skip(
        "Requires at least one valid, already-authenticated Databricks CLI "
        "profile configured locally."
    )


def _require_two_valid_databricks_profiles() -> tuple[
    _DatabricksAuthProfile, _DatabricksAuthProfile
]:
    """
    Return two distinct, valid, already-authenticated local profiles, or
    skip if fewer than two exist.
    """
    valid_profiles: list[_DatabricksAuthProfile] = [
        profile
        for profile in _require_databricks_profiles()
        if profile.get("valid")
    ]
    if len(valid_profiles) < 2:
        pytest.skip(
            "Requires at least two valid, already-authenticated Databricks "
            "CLI profiles configured locally."
        )
    return valid_profiles[0], valid_profiles[1]


def test_databricks_auth_profiles() -> None:
    """
    `_databricks_auth_profiles` parses real `databricks auth profiles`
    output into the documented shape.
    """
    profiles: list[_DatabricksAuthProfile] = _require_databricks_profiles()
    assert all(
        ("name" in profile) and ("host" in profile) for profile in profiles
    )


def test_databricks_auth_profiles_timeout_expires() -> None:
    """
    A near-zero `timeout` causes `_databricks_auth_profiles` to raise
    `TimeoutExpired`.
    """
    with pytest.raises(TimeoutExpired):
        _databricks_auth_profiles(timeout=1e-6)


def test_databricks_auth_profiles_timeout_cache_key() -> None:
    """
    Distinct `timeout` values are distinct `_databricks_auth_profiles`
    cache keys: each triggers its own real CLI round-trip (a cache miss),
    while repeating the same `timeout` hits cache.
    """
    _require_databricks_profiles()
    _databricks_auth_profiles.cache_clear()
    _databricks_auth_profiles(timeout=None)
    misses_after_first: int = _databricks_auth_profiles.cache_info().misses
    _databricks_auth_profiles(timeout=30)
    misses_after_second: int = _databricks_auth_profiles.cache_info().misses
    assert misses_after_second == misses_after_first + 1
    _databricks_auth_profiles(timeout=30)
    assert _databricks_auth_profiles.cache_info().misses == misses_after_second


def test_get_host_profile() -> None:
    """
    A configured profile's host resolves back to its profile name.
    """
    profile: _DatabricksAuthProfile = _require_databricks_profiles()[0]
    assert _get_host_profile(profile["host"]) == profile["name"]


def test_databricks_auth_describe() -> None:
    """
    `_databricks_auth_describe` reports success for the already
    authenticated local profile.
    """
    profile: _DatabricksAuthProfile = _require_valid_databricks_profile()
    assert (
        _databricks_auth_describe(profile=profile["name"]).get("status")
        == "success"
    )


def test_databricks_auth_describe_timeout_expires() -> None:
    """
    A near-zero `timeout` causes `_databricks_auth_describe` to raise
    `TimeoutExpired`.
    """
    profile: _DatabricksAuthProfile = _require_valid_databricks_profile()
    with pytest.raises(TimeoutExpired):
        _databricks_auth_describe(profile=profile["name"], timeout=1e-6)


def test_databricks_auth_login_skips_when_already_authenticated() -> None:
    """
    With `force=False` (the default), an already-authenticated profile
    short-circuits rather than attempting a fresh login. Verified by
    comparing wall-clock time against a real `_databricks_auth_login` call
    measured in the same run, rather than a fixed threshold, since a real
    `databricks auth login` round-trip (over a second, empirically) is only
    ~2-3x slower than the `_databricks_auth_describe` short-circuit check
    (behind `force=False`) on this machine — not the multiple-orders-of-
    magnitude gap a `functools.cache` hit gives, so a hard-coded absolute
    threshold would be flaky across machines/networks.
    """
    profile: _DatabricksAuthProfile = _require_valid_databricks_profile()
    start: float = monotonic()
    databricks_auth_login(profile=profile["name"])
    short_circuit_seconds: float = monotonic() - start
    _databricks_auth_login.cache_clear()
    start = monotonic()
    _databricks_auth_login(profile=profile["name"])
    real_login_seconds: float = monotonic() - start
    assert short_circuit_seconds < (real_login_seconds * 0.75)


def test_databricks_auth_login_env_fallback() -> None:
    """
    With no explicit `host`/`profile`/`target`, `DATABRICKS_HOST` is
    honored when resolving whether a login is already valid.
    """
    profile: _DatabricksAuthProfile = _require_valid_databricks_profile()
    env: dict[str, str] = os.environ.copy()
    try:
        os.environ["DATABRICKS_HOST"] = profile["host"]
        os.environ.pop("DATABRICKS_CONFIG_PROFILE", None)
        databricks_auth_login()
        assert (
            _databricks_auth_describe(host=profile["host"]).get("status")
            == "success"
        )
    finally:
        os.environ.clear()
        os.environ.update(env)


def test_databricks_auth_login_timeout_expires() -> None:
    """
    A near-zero `timeout` causes `databricks_auth_login` to raise
    `TimeoutExpired`, via its internal `_databricks_auth_describe` status
    check, before any interactive login is ever attempted.
    """
    profile: _DatabricksAuthProfile = _require_valid_databricks_profile()
    with pytest.raises(TimeoutExpired):
        databricks_auth_login(profile=profile["name"], timeout=1e-6)


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
    Verified by wall-clock time, measured live in this test: a
    `functools.cache` hit takes microseconds, while a real
    `databricks auth login` round-trip takes over a second — a gap of
    several orders of magnitude, wide enough that this can't pass by
    coincidence regardless of machine or network speed.

    The cache is seeded by calling the private `_databricks_auth_login`
    directly first, since the public `databricks_auth_login` would
    otherwise short-circuit on its own "already authenticated" check and
    never populate the cache at all.
    """
    profile: _DatabricksAuthProfile = _require_valid_databricks_profile()
    # Match the exact cache key `databricks_auth_login` uses internally
    # (`**get_prefixed_environ("DATABRICKS_")` is part of the key), so
    # seeding this entry actually collides with the one `force=True` must
    # evict below.
    _databricks_auth_login.cache_clear()
    _databricks_auth_login(
        host=None,
        profile=profile["name"],
        target=None,
        **get_prefixed_environ("DATABRICKS_"),
    )
    start: float = monotonic()
    _databricks_auth_login(
        host=None,
        profile=profile["name"],
        target=None,
        **get_prefixed_environ("DATABRICKS_"),
    )
    cached_call_seconds: float = monotonic() - start
    start = monotonic()
    databricks_auth_login(profile=profile["name"], force=True)
    forced_call_seconds: float = monotonic() - start
    assert forced_call_seconds > (cached_call_seconds * 10)


@pytest.mark.skipif(
    bool(os.getenv("CI")),
    reason=(
        "Forcing a real login requires an interactive OAuth browser flow, "
        "so this can only be run supervised, outside CI."
    ),
)
def test_databricks_auth_login_force_clears_cache_for_other_profiles() -> None:
    """
    `_databricks_auth_login.cache_clear()` wipes the entire cache, not just
    the entry for the forced profile. Confirm an unrelated, already-cached
    profile is evicted too — its next call takes real-login time rather
    than remaining a cache hit — verified by wall-clock time for the same
    reason as `test_databricks_auth_login_force_reauthenticates`.
    """
    first: _DatabricksAuthProfile
    second: _DatabricksAuthProfile
    first, second = _require_two_valid_databricks_profiles()
    # Match the exact cache key `databricks_auth_login` uses internally
    # (`**get_prefixed_environ("DATABRICKS_")` is part of the key), so
    # seeding these entries actually collides with what `force=True` must
    # evict below.
    _databricks_auth_login.cache_clear()
    _databricks_auth_login(
        host=None,
        profile=first["name"],
        target=None,
        **get_prefixed_environ("DATABRICKS_"),
    )
    _databricks_auth_login(
        host=None,
        profile=second["name"],
        target=None,
        **get_prefixed_environ("DATABRICKS_"),
    )
    start: float = monotonic()
    _databricks_auth_login(
        host=None,
        profile=second["name"],
        target=None,
        **get_prefixed_environ("DATABRICKS_"),
    )
    cached_call_seconds: float = monotonic() - start
    databricks_auth_login(profile=first["name"], force=True)
    start = monotonic()
    _databricks_auth_login(
        host=None,
        profile=second["name"],
        target=None,
        **get_prefixed_environ("DATABRICKS_"),
    )
    after_force_call_seconds: float = monotonic() - start
    assert after_force_call_seconds > (cached_call_seconds * 10)


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
