# Plan: Close Missing Test Coverage

Implements the gaps identified in
[docs/superpowers/specs/2026-07-21-missing-test-coverage-design.md](../specs/2026-07-21-missing-test-coverage-design.md),
prioritizing the `databricks_auth_login`/`force` parameter this branch
introduces.

## Sequencing

1. Write the P0 Databricks auth-internals tests.
2. Write the P1 tests (`get_dbutils`, `op_signin`/`iter_op_account_list`,
   both CLI entry points, `which_winget`).
3. Write the P2 callback unit test (no dependencies, can slot in anytime).
4. Write the P2 SDK-token 1Password test.

The bundle-target test and the 1Password Connect test are deferred — see
below.

## P0 tests (`tests/test_databricks.py`)

Add:

- `test_databricks_auth_login_force_reauthenticates` — `force=True`
  triggers a real second CLI call rather than returning the cached result.
- `test_databricks_auth_login_force_clears_cache_for_other_profiles` —
  forcing a re-login for one profile evicts and transparently re-populates
  another cached profile's state, without corrupting it.
- `test_databricks_auth_login_skips_when_already_authenticated`
- `test_databricks_auth_login_env_fallback`
- `test_databricks_auth_describe`
- `test_get_host_profile`
- `test_databricks_auth_profiles`
- `test_which_databricks`
- `test_databricks_cli_get_command`
- `test_databricks_cli_install_command`

`test_databricks_auth_login_target` is deferred — see below. Remove the
`# pragma: no cover` markers from each function once it's actually
exercised.

## P1 tests

- `tests/test_onepassword.py`: `test_iter_op_account_list`,
  `test_op_signin_no_account_iterates_all_accounts`,
  `test_op_signin_with_explicit_account`, `test_onepassword_cli_get_command`,
  `test_onepassword_cli_install_command`.
- `tests/test_databricks.py`: `test_get_dbutils_returns_real_client_dbutils`.
- Wherever `test_install_brew` currently lives: `test_which_winget`,
  skipped on non-Windows platforms.

## P2 tests

- `tests/test_callback.py`:
  `test_callback_argument_dropped_when_target_explicit`. Pure unit test, no
  external resource, no blockers.
- `tests/test_onepassword.py`:
  `test_async_read_onepassword_secret_via_sdk_token`, covering
  `_async_resolve_resource` via a real service-account token (no Connect
  server required).

## Deferred

- `test_databricks_auth_login_target` — would need a real Databricks Asset
  Bundle fixture to exercise a narrow, already fail-safe fallback branch.
  Not worth the ongoing fixture upkeep.
- `test_read_onepassword_secret_via_connect` — needs a running 1Password
  Connect server, which is infrastructure most callers of this library
  don't run. Revisit only if that infrastructure exists for other reasons.

## Verification

- Run `make test` after each step, not just at the end.
- Confirm the coverage report no longer flags the functions whose
  `# pragma: no cover` markers were removed.
- Re-run the suite with `CI` set in the environment to confirm the
  interactive-only branches (see the existing `test_get_secret` pattern)
  still skip correctly.
