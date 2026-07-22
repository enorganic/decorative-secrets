# Plan: `timeout` Propagation to `check_output` + `os.environ` Cache-Key Narrowing

Implements
[docs/superpowers/specs/2026-07-21-check-output-timeout-design.md](../specs/2026-07-21-check-output-timeout-design.md).
Two intertwined changes, done together because they touch the same
functions and the same `@cache`-key surface:

1. Thread `timeout: float | None = None` through every function whose
   call chain reaches `check_output`/`check_call`.
2. Replace the four `**os.environ` cache-key-widening splats with
   `**get_prefixed_environ("DATABRICKS_" | "OP_")`.

## Sequencing

Bottom-up per module, tests alongside each function (not deferred to the
end) — confirming `TimeoutExpired` propagates one layer at a time is far
easier than debugging the whole chain after every function has changed.
`make format && make test` after every step.

1. `subprocess.py` cleanup.
2. `_utilities.py`: `timeout` on the three leaf functions, plus the new
   `get_prefixed_environ` helper.
3. `databricks.py`, bottom-up.
4. `onepassword.py`, bottom-up.
5. Full-suite verification.

## Step 1 — `subprocess.py` cleanup

- Normalize parameter order across all three `@overload` stubs and the
  implementation of `check_output` to
  `cwd, input, env, suppress_stderr, shell, timeout, echo` (`timeout`
  currently sits in an inconsistent position in one overload).
- `check_output`/`check_call` themselves already have `timeout` wired to
  `subprocess.run` — no functional change here, ordering only.
- Test: confirm `tests/test_subprocess.py` covers `timeout` raising
  `subprocess.TimeoutExpired` on both `check_output` and `check_call`
  (via a real long-running command), and that a generous timeout doesn't
  change a successful result vs. an untimed call. Add if missing.

## Step 2 — `_utilities.py`

In call order (each depends on the previous within this file):

1. `install_brew(timeout: float | None = None)` → forward to its one
   `check_output` call.
2. `which_brew(timeout=None)` → forward to both `check_output` calls and
   to `install_brew(timeout=timeout)`.
3. `which_winget(timeout=None)` → forward to its one `check_output` call.
4. New: `get_prefixed_environ(*prefixes: str) -> dict[str, str]` (see
   spec for body) — no dependents yet, but lives here so `databricks.py`/
   `onepassword.py` can import it in steps 3–4.

Tests (`tests/test__utilities.py`):
- `timeout` forwarding for `install_brew`/`which_brew`/`which_winget`:
  near-zero timeout against the real `brew`/`winget`/install-script
  invocation raises `TimeoutExpired`, platform-gated like the existing
  tests for these.
- `get_prefixed_environ`: pure unit test (no external resource, no
  mocking restriction) — single prefix, multiple prefixes, no match →
  empty dict.

## Step 3 — `databricks.py`, bottom-up

Add `timeout: float | None = None` and forward at each level, in this
order (matches the call graph):

1. `_install_sh_databricks_cli` — forward to its `check_call`.
2. `_install_databricks_cli` — forward to `which_winget`, `which_brew`,
   its four `check_output` calls, and `_install_sh_databricks_cli`.
3. `which_databricks` — forward to its `check_output` call and to
   `_install_databricks_cli`.
4. `_databricks_auth_profiles` (`@cache`) — forward to `which_databricks`
   and its `check_output` call.
5. `_get_host_profile` (`@cache`) — forward to `_databricks_auth_profiles`.
6. `_databricks_auth_describe` — finish the partial work already in the
   working tree: forward `timeout` on the `else:` branch's `check_output`
   call too (currently missing), and on the now-`timeout`-aware
   `which_databricks()`/`_get_host_profile(host)` calls.
7. `_databricks_bundle_summary` — forward to `which_databricks` and its
   `check_output` call.
8. `_databricks_auth_login_target` — forward to `_databricks_auth_login`
   and `_databricks_bundle_summary`.
9. `_databricks_auth_login` (`@cache` + `@retry`) — forward to
   `which_databricks`, `_get_host_profile`, both `check_call` calls,
   `_databricks_auth_login_target`, `_databricks_auth_profiles`, and the
   recursive self-call.
10. `databricks_auth_login` — finish the partial work already present:
    fix the duplicated `Raises: CalledProcessError` docstring line and
    trailing whitespace; let `make format` settle the wrapping of the
    final `_databricks_auth_login(...)` call. **Also**: replace
    `**os.environ` with `**get_prefixed_environ("DATABRICKS_")` at this
    call site.
11. `_get_env_databricks_workspace_client` (`@cache`) — add `timeout`,
    forward to `databricks_auth_login` (this call currently only passes
    `host`/`profile`).
12. `get_databricks_workspace_client` — add `timeout`, forward. **Also**:
    replace `**os.environ` with `**get_prefixed_environ("DATABRICKS_")`
    at its `_get_env_databricks_workspace_client(...)` call.
13. `get_dbutils` — add `timeout`, forward.
14. `_get_secret` (`@cache`) — add `timeout`, forward.
15. `get_databricks_secret` — add `timeout`, forward. **Also**: replace
    `**os.environ` with `**get_prefixed_environ("DATABRICKS_")` at its
    `_get_secret(...)` call.
16. `_get_scope_key_secret` — add `timeout`, forward to
    `get_databricks_secret`.
17. `DatabricksWorkspaceClientArguments` — add `timeout: float | None =
    None` field. `apply_databricks_secrets_arguments` needs no other
    change: it already unpacks the dataclass via `asdict(...)` into the
    `partial(_get_scope_key_secret, ...)`.
18. `main()` (CLI) — add `--timeout FLOAT` to both `install` and `get`
    argparse subcommands; forward to `_install_databricks_cli(timeout=...)`
    / `get_databricks_secret(..., timeout=...)`.

Tests (`tests/test_databricks.py`), added alongside the corresponding
step above rather than all at once:
- `timeout` forwarding: near-zero timeout against the real CLI
  (`databricks_env` fixture) raises `TimeoutExpired` for
  `which_databricks`, `_databricks_auth_profiles`, `_databricks_auth_describe`,
  `databricks_auth_login`, `get_databricks_secret`. Generous timeout still
  returns the same successful result as the existing untimed tests.
- `apply_databricks_secrets_arguments`: a `DatabricksWorkspaceClientArguments(timeout=...)`
  with a near-zero value causes the decorated function's lookup to
  raise/propagate `TimeoutExpired` (or surface via `ArgumentsResolutionError`,
  matching how other callback failures already surface).
- Cache-key regression guard (pick one `@cache`d function, e.g.
  `_databricks_auth_login`): two calls with different `timeout` values
  each do a real round-trip; two calls with the same `timeout` hit cache.
- Cache-key narrowing regression guard: for `get_databricks_secret`,
  changing an irrelevant env var (e.g. `PATH`) between two otherwise
  identical calls still hits cache; changing a `DATABRICKS_*` var busts
  it.

## Step 4 — `onepassword.py`, bottom-up

1. `_install_op` — forward `timeout` to `which_winget`, `which_brew`,
   both `check_output` calls.
2. `which_op` — forward to its `check_output` call and to `_install_op`.
3. `_op_signin` (`@cache`) — forward to `which_op` and its `check_output`
   call.
4. `iter_op_account_list` — forward to `which_op` and its `check_output`
   call.
5. `op_signin` — forward to `_op_signin`, `iter_op_account_list`,
   `which_op`.
6. `async_read_onepassword_secret` (`@alru_cache`) — forward to
   `op_signin`, `which_op`, its `check_output` call. No change needed to
   the `_async_resolve_resource`/`_async_resolve_connect_resource`
   branches (no `check_output` there).
7. `_read_onepassword_secret` (`@cache`) — same as above.
8. `get_onepassword_secret` / `read_onepassword_secret` alias — add
   `timeout`, forward to `_read_onepassword_secret`. **Also**: replace
   `**os.environ` with `**get_prefixed_environ("OP_")` at this call site.
9. `ApplyOnepasswordArgumentsOptions` — add `timeout: float | None =
   None` field; thread it through the existing conditional-kwargs
   `partial(read_onepassword_secret_, ...)` /
   `partial(async_read_onepassword_secret_, ...)` construction in
   `apply_onepassword_arguments` (same pattern as `account`/`token`/`host`).
10. `main()` (CLI) — add `--timeout FLOAT` to both `install` and `get`
    subcommands; forward to `_install_op(timeout=...)` /
    `read_onepassword_secret(..., timeout=...)`.

Tests (`tests/test_onepassword.py`), alongside each step:
- `timeout` forwarding for `which_op`, `op_signin`, `iter_op_account_list`,
  `get_onepassword_secret`/`read_onepassword_secret`,
  `async_read_onepassword_secret` (`onepassword_vault` fixture),
  near-zero → `TimeoutExpired`, generous → unchanged successful result.
- `apply_onepassword_arguments` with `ApplyOnepasswordArgumentsOptions(timeout=...)`,
  same pattern as the Databricks decorator test above.
- Cache-key regression guard for `_op_signin` (or `_read_onepassword_secret`):
  different `timeout` → real round-trip each time; same `timeout` → cache
  hit.
- Cache-key narrowing regression guard for `get_onepassword_secret`:
  irrelevant env var change still hits cache; an `OP_*` var change busts
  it.

## Out of scope (per spec)

- `callback.py` — unchanged.
- `_async_resolve_resource`, `_async_resolve_connect_resource`,
  `_resolve_connect_resource` — HTTP clients, not `check_output`.
- `environment.py`, `defaults.py`, `errors.py`, `utilities.py` — no
  `check_output` in their call chains.

## Verification

- `make format` and `make test` after each of the four steps, not just at
  the end.
- Confirm no `# pragma: no cover` marker is silently masking a new,
  untested branch introduced by the `timeout`/env-narrowing changes.
- Spot-check that `_databricks_auth_login`'s and `_read_onepassword_secret`'s
  cache behavior (both `timeout`-key-widening and the env-prefix
  narrowing) matches the "Cache-key regression guard" tests above —
  these two are the highest-risk spots for a silent cache-correctness
  regression.
