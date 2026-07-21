# Missing Test Coverage — Spec

This document inventories gaps in the current test suite (`tests/`) as of
branch `databricks-auth-login-force-parameter`.

## Ground rules

Per existing project convention (see `tests/test_databricks.py`,
`tests/test_onepassword.py`, `tests/conftest.py`), **any test that exercises
a real external resource — the Databricks CLI/workspace, the 1Password
CLI/vault/Connect server, Homebrew, WinGet, or a network install script —
must be a genuine integration test against the real thing.** No
`unittest.mock`/monkeypatching of those systems. The existing
`databricks_env` and `onepassword_vault` fixtures already provide real
credentials for this purpose. New tests should reuse them rather than
invent parallel mocked equivalents.

`monkeypatch`/`caplog`/`capsys` remain fine for pure internal control flow
that touches no external resource (e.g. `sys.argv` dispatch in
`__main__.py`, which is already tested this way) — that's not what "no
mocks" is guarding against.

## P0 — `databricks_auth_login` and the `force` parameter (0% covered)

Every function in the call chain is marked `# pragma: no cover` and
untested: `databricks_auth_login`, `_databricks_auth_login`,
`_databricks_auth_login_target`, `_databricks_auth_describe`,
`_databricks_bundle_summary`, `_databricks_auth_profiles`,
`_get_host_profile`, `which_databricks`.

`_databricks_auth_login` is memoized with `@cache`.
`databricks_auth_login(force=True)` calls
`_databricks_auth_login.cache_clear()` before invoking it, so a forced call
always triggers a fresh CLI invocation rather than returning a memoized
result. `cache_clear()` wipes the entire cache though, not just the entry
for the current `host`/`profile`/`target`, so a forced login for one
profile also evicts (and causes transparent re-population of) any other
cached profile's state. That side effect needs its own test rather than
being assumed correct.

None of these functions have their own fixture-provisioned Databricks CLI
profile — they depend on `~/.databrickscfg` already having at least one
configured profile. This project's CI never runs `databricks auth login`
or `databricks configure` (it only sets `DATABRICKS_CLIENT_ID`/`_SECRET`/
`_HOST` for direct OAuth M2M auth via the SDK). With no `~/.databrickscfg`
at all, `databricks auth profiles -o json` **exits non-zero** there — it
does not return an empty list. Tests in this section must catch
`subprocess.CalledProcessError` around that call (not just check for an
empty/invalid-only result) and skip rather than crash. (Confirmed against
a real CI failure: https://github.com/enorganic/decorative-secrets/actions/runs/29863219875 —
an initial implementation that only handled the empty-list case still
failed in CI.)

- `test_databricks_auth_login_force_reauthenticates` — using real
  credentials (`databricks_env`), call `databricks_auth_login(profile=...)`
  once, then again with `force=True`. Assert observable evidence of a
  second real CLI round-trip (e.g. wall-clock duration comparable to an
  actual `databricks auth login` call rather than a near-instant cache hit,
  and/or a changed mtime on the relevant `~/.databrickscfg` profile entry).
  A status/`_databricks_auth_describe`-based assertion is not sufficient
  here: it reads real on-disk CLI state, not the Python-level cache, so it
  can't distinguish a cache hit from a fresh login and would pass even if
  `cache_clear()` were removed entirely.
- `test_databricks_auth_login_force_clears_cache_for_other_profiles` —
  cache two profiles, force-relogin one, and prove the other's cache entry
  was evicted too via the same wall-clock-timing approach as the sibling
  test above (a repeat call for the untouched profile must take real-login
  time, not cache-hit time, after the other profile's forced relogin). The
  same status/describe-based pitfall applies here — that approach cannot
  detect whether the Python-level cache was actually cleared.
- `test_databricks_auth_login_skips_when_already_authenticated` — with
  `force=False` (default) and a profile already authenticated, confirm no
  fresh login is attempted (fast return).
- `test_databricks_auth_login_env_fallback` — with no `host`/`profile`/
  `target` argument, confirm `DATABRICKS_HOST`/`DATABRICKS_CONFIG_PROFILE`
  env vars are honored (mirrors the existing env-fallback branch already
  covered for `get_databricks_secret` in `test_get_secret`).
- `test_databricks_auth_describe` — call `_databricks_auth_describe`
  against the real, already-authenticated profile/host and assert
  `status == "success"`.
- `test_get_host_profile` — assert a known configured profile's host
  resolves back to its profile name.
- `test_databricks_auth_profiles` — assert real `databricks auth profiles
  -o json` output parses into the expected shape and includes the test
  profile.
- `test_which_databricks` — assert it returns a working `databricks`
  executable (parallel to the existing `test_which_op`).
- `test_databricks_auth_login_target` — deferred. Exercises the
  bundle-target retry branch in `_databricks_auth_login` and
  `_databricks_auth_login_target`, which would require maintaining a real
  Databricks Asset Bundle (`databricks.yml`) fixture. That branch already
  fails safe (`suppress(CalledProcessError)`), so the ongoing fixture
  upkeep isn't worth the coverage of this narrow fallback path.
- `test_databricks_cli_get_command` / `test_databricks_cli_install_command`
  — the `main()` in `databricks.py` (argparse `get`/`install` subcommands)
  has zero coverage. Invoke it end-to-end (real `sys.argv` + real env)
  against a real secret from `databricks_env`, and assert stdout matches
  `get_databricks_secret(...)`.

## P1 — `get_dbutils` (0% direct coverage)

Only exercised indirectly through `get_databricks_secret`.

- `test_get_dbutils_returns_real_client_dbutils` — call `get_dbutils()`
  directly against the real workspace client from `databricks_env` and
  assert it exposes a working `.secrets.get(...)`.

## P1 — 1Password: `op_signin` / `iter_op_account_list` (0% direct coverage)

This project's CI only authenticates 1Password via `OP_SERVICE_ACCOUNT_TOKEN`
— it never runs an interactive `op signin`, so `op account list` (and
therefore `iter_op_account_list()`) legitimately yields nothing there. Tests
in this section must skip when there are no interactively-registered
accounts, rather than asserting on or indexing into an empty list
(confirmed against the same CI run referenced above: an initial
implementation without this guard failed there).

- `test_iter_op_account_list` — assert the real configured 1Password
  account(s) are yielded.
- `test_op_signin_no_account_iterates_all_accounts` — clear `OP_ACCOUNT`,
  call `op_signin()` with no argument, assert it signs in to at least one
  real account and returns a usable `op` path.
- `test_op_signin_with_explicit_account` — pass an explicit account and
  assert sign-in succeeds against it.

## P1 — onepassword CLI entry point (0% coverage)

- `test_onepassword_cli_get_command` — invoke `onepassword.py`'s `main()`
  `get` subcommand against a real vault reference (`onepassword_vault`),
  assert stdout matches `read_onepassword_secret(...)`.
- `test_onepassword_cli_install_command` — parallel to the existing
  `_install_op` test, but through the CLI entry point.

## P1 — `which_winget` (0% coverage, Windows-only)

No test exists at all (unlike `which_brew`, which has
`test_install_brew`). Add a Windows-only integration test analogous to
`test_install_brew`:

- `test_which_winget` — on `sys.platform.startswith("win")`, assert it
  returns a working `winget` executable, and skip otherwise.

## P2 — 1Password Connect paths (0% coverage, deferred)

`_resolve_connect_resource` and `_async_resolve_connect_resource` need a
running 1Password Connect server plus token — self-hosted infrastructure
most callers of this library don't run. Deferred unless that
infrastructure already exists for other reasons:

- `test_read_onepassword_secret_via_connect` — set `OP_CONNECT_HOST`/
  `OP_CONNECT_TOKEN`, call `get_onepassword_secret(...)`, assert it matches
  the CLI-based read.

## P2 — pure-logic gap (no external resource, plain unit test)

`apply_callback_arguments` (`src/decorative_secrets/callback.py:134-149,
204-205`) drops a lookup-argument (e.g. `client_id_databricks_secret`) from
`kwargs` when the corresponding target parameter (`client_id`) was already
explicitly supplied. This branch has no test:

- `test_callback_argument_dropped_when_target_explicit` — call a decorated
  function with both `x=5` and `x_lookup_arg=...` set. Assert the callback
  is never invoked and the explicit value wins.

## Known issue found during implementation (not a missing-test gap)

`_install_op` (`src/decorative_secrets/onepassword.py:145`) maps any
`brew install 1password-cli` failure on macOS — including the common
already-installed case — to `OnePasswordCommandLineInterfaceNotInstalledError`.
The existing `test_install_op` and the new `test_onepassword_cli_install_command`
both suppress that exception rather than asserting correct idempotent
behavior, so neither would catch a real regression here. This is a
pre-existing source characteristic, not something introduced while closing
these test gaps, and fixing it means redesigning `_install_op`'s error
handling — out of scope for this spec. Flagged for a separate follow-up.

## Already adequately covered — no action needed

`_utilities.py`, `utilities.py` (`timeout`, `retry`, logging, `as_*`
decorators), `callback.py`, `defaults.py`, `errors.py`, `environment.py`,
`subprocess.py` (including `which_winget`), and `__main__.py` all have
solid test coverage today, including edge cases. `which_brew`/
`install_brew` are already integration-tested against the real Homebrew
installer with appropriate per-platform skips. `_async_resolve_resource`
(the `onepassword-sdk` token path, no Connect server required) is covered
by `test_async_read_onepassword_secret_via_sdk_token`.
