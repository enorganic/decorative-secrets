# `timeout` Propagation to `check_output` — Spec

This document specifies adding a `timeout: float | None = None` parameter
to every function in `src/decorative_secrets/` whose call chain reaches
`decorative_secrets.subprocess.check_output`, so a caller can bound how
long any underlying CLI invocation (`databricks`, `op`, `brew`, `winget`,
install scripts) is allowed to run, all the way down to
`subprocess.run(..., timeout=...)`.

Branch: `check-output-timeout`. This spec covers the working tree as of
this branch, including the partial, uncommitted start already present in
`subprocess.py` and `databricks.py`.

It also covers a related cleanup discovered while auditing the same
`@cache`-key surface this change touches: four call sites splat the
*entire* `os.environ` into a cached function just to widen its cache key,
when only a prefix-identifiable subset of env vars are ever relevant.
See "Cache-key narrowing" below.

## Ground rules

> **Superseded by implementation**: `timeout` is keyword-only everywhere
> (not just where convenient), and every *public* function defaults to
> `60` rather than `None` — `None` remains the default only on private
> (underscore-prefixed) helpers, which always receive an explicit value
> forwarded from their public caller. See `docs/contributing.md`'s
> Conventions section for the final rule.

- `timeout` is `float | None`, matching `subprocess.run`'s own `timeout`
  semantics (`subprocess.TimeoutExpired` on expiry).
- `timeout` is always keyword-only.
- Every function that calls `check_output`/`check_call`, or that calls
  another function in this library which (transitively) does, must accept
  and forward `timeout`. No link in a call chain may silently drop it.
- Do not conflate this with `decorative_secrets.utilities.timeout`, the
  `@timeout(seconds)` decorator used elsewhere in the codebase (signal/
  thread-based wall-clock timeout for arbitrary Python code). That is a
  different mechanism solving a different problem. This spec is only
  about the `subprocess.run(timeout=...)` argument threaded through
  `check_output`/`check_call`.
- **Caching interaction**: several functions in this chain are `@cache`d
  (`which_brew`, `which_winget`, `_databricks_auth_profiles`,
  `_get_host_profile`, `_databricks_auth_login`,
  `_get_env_databricks_workspace_client`, `_get_secret`, `_op_signin`,
  `_read_onepassword_secret`) or `@alru_cache`d
  (`async_read_onepassword_secret`). Adding `timeout` as a parameter makes
  it part of the cache key, same as the existing `host`/`profile`/`**env`
  parameters already do. Two calls that differ only by `timeout` will
  therefore populate separate cache entries rather than sharing one. This
  is consistent with existing precedent in this codebase (e.g.
  `_databricks_auth_login` is already called with the full `**os.environ`
  as cache-key-widening kwargs) and is called out here so it isn't
  mistaken for a bug later. See also the `os.environ` narrowing below,
  which shrinks — but does not eliminate — this same cache-key surface.
- **`apply_databricks_secrets_arguments` / `apply_onepassword_arguments`**:
  the lookup callback these decorators wire up
  (`_get_scope_key_secret`, `read_onepassword_secret`) is invoked by
  `apply_callback_arguments` (`callback.py`) with exactly one positional
  argument — the scope/key tuple or resource string. There is no
  mechanism today for a per-call keyword argument (like a per-invocation
  `timeout`) to reach the callback through that decorator. Per-call
  override is therefore out of scope. Instead, add `timeout` to the
  existing options dataclasses (`DatabricksWorkspaceClientArguments`,
  `ApplyOnepasswordArgumentsOptions`) that are already threaded into the
  callback via `functools.partial` at decoration time (mirrors how
  `host`/`profile`/`account`/`token` are handled today). This gives a
  decorator-level (fixed at decoration time), not per-call, timeout.

## Already done (uncommitted, in working tree)

`subprocess.py`:
- `check_output` — `timeout` param added to all three `@overload`
  signatures and the implementation; forwarded to both `subprocess.run(...)`
  call sites (`suppress_stderr=True` and `suppress_stderr=False` branches).
  Docstring `Raises:` section updated.
- `check_call` — `timeout` param added and forwarded to `check_output`.

Cleanup needed on what's already there:
- The three `@overload` stubs for `check_output` place `timeout` in an
  inconsistent position relative to `echo` (before `echo` in two overloads,
  after in the third, and the implementation itself). Normalize the
  parameter order across all four signatures to:
  `cwd, input, env, suppress_stderr, shell, timeout, echo` (implementation
  order), so the overloads and implementation read identically.

`databricks.py`:
- `_databricks_auth_describe` — `timeout` param added, but only forwarded
  on the `if host or profile or target:` branch's `check_output` call
  (line ~331-344). The `else:` branch's `check_output` call (line ~348-351,
  the no-host/profile/target auto-select path) does not forward `timeout`.
  Also, `which_databricks()` (line ~328) and `_get_host_profile(host)`
  (line ~327) are called without `timeout` — once those two gain a
  `timeout` parameter (see below), this function must forward to them too.
- `databricks_auth_login` — `timeout` param added and forwarded to
  `_databricks_auth_describe(timeout=timeout)` and
  `_databricks_auth_login(timeout=timeout, ...)`. Docstring has a
  duplicated `CalledProcessError` entry in `Raises:` (copy/paste artifact)
  and trailing whitespace on the blank line after the `Args`/`Parameters`
  block — both need cleanup. The final `return _databricks_auth_login(...)`
  call is also awkwardly line-wrapped (`timeout=timeout,` and `**os.environ`
  split across lines in a way `make format` will likely reflow) — let
  `make format` settle it rather than hand-wrapping.

Neither `_databricks_auth_login` itself, `which_databricks`,
`_get_host_profile`, nor `_databricks_auth_profiles` — all in the call
chain below `_databricks_auth_describe`/`databricks_auth_login` — have
been touched yet. See below.

## Cache-key narrowing: `**os.environ` → prefix-filtered

Unrelated to `timeout`, but touching the same cache-key mechanism
discussed above, so bundled into this pass: four call sites currently
splat the *entire* process environment into a `@cache`d function purely
to widen its cache key (so the cache is invalidated whenever any env var
changes) — even though only a small, prefix-identifiable subset of env
vars are ever relevant to that function's operation:

| Call site | Splats | Cached callee | Relevant prefix |
|---|---|---|---|
| `databricks_auth_login` → `_databricks_auth_login(..., **os.environ)` (`databricks.py:497`) | full `os.environ` | `_databricks_auth_login` (`@cache` + `@retry`) | `DATABRICKS_` |
| `get_databricks_workspace_client` → `_get_env_databricks_workspace_client(..., **os.environ)` (`databricks.py:680`) | full `os.environ` | `_get_env_databricks_workspace_client` (`@cache`) | `DATABRICKS_` |
| `get_databricks_secret` → `_get_secret(..., **os.environ)` (`databricks.py:939`) | full `os.environ` | `_get_secret` (`@cache`) | `DATABRICKS_` |
| `get_onepassword_secret`/`read_onepassword_secret` → `_read_onepassword_secret(..., **os.environ)` (`onepassword.py:397`) | full `os.environ` | `_read_onepassword_secret` (`@cache`) | `OP_` |

Every env var explicitly read anywhere in `databricks.py` is
`DATABRICKS_HOST`, `DATABRICKS_CONFIG_PROFILE`, `DATABRICKS_CLIENT_ID`, or
`DATABRICKS_CLIENT_SECRET` — all `DATABRICKS_`-prefixed. Every env var
explicitly read in `onepassword.py` is `OP_ACCOUNT`,
`OP_SERVICE_ACCOUNT_TOKEN`, `OP_CONNECT_HOST`, or `OP_CONNECT_TOKEN` — all
`OP_`-prefixed. Filtering by prefix rather than enumerating these exact
names is deliberate: `_get_env_databricks_workspace_client` constructs a
`databricks.sdk.WorkspaceClient`, which itself reads additional
`DATABRICKS_*` variables internally (e.g. `DATABRICKS_TOKEN`,
`DATABRICKS_AUTH_TYPE`, `DATABRICKS_AZURE_*`) that never appear as a
literal `os.getenv(...)` call in this repo; likewise the `op` CLI consults
dynamically-named `OP_SESSION_<account-uuid>` variables. A fixed name list
would miss both. A prefix filter catches them without needing to track
the SDK's/CLI's full env var surface by hand.

Add a small helper (`_utilities.py`, alongside `get_errors`/
`unwrap_function`):

```python
def get_prefixed_environ(*prefixes: str) -> dict[str, str]:
    """
    Return the subset of `os.environ` whose variable names start with one
    of `prefixes`, for use as cache-key-widening `**kwargs` — narrower
    than splatting the entire environment, but still cache-busts whenever
    a variable actually relevant to the operation changes.
    """
    key: str
    value: str
    return {
        key: value
        for key, value in os.environ.items()
        if key.startswith(prefixes)
    }
```

(`str.startswith` accepts a tuple, so a single `prefixes` tuple argument
covers the multi-prefix case too, though none of the four call sites need
more than one prefix today.)

Then replace each `**os.environ` above with
`**get_prefixed_environ("DATABRICKS_")` (three call sites in
`databricks.py`) or `**get_prefixed_environ("OP_")` (`onepassword.py`).
The receiving functions' own `**env: str,  # noqa: ARG001` parameters are
unchanged — they're still unused, just now populated with fewer entries.

This does not change behavior of what the functions *do*, only how
precisely their cache invalidates: today, changing e.g. `PATH` or
`EDITOR` needlessly busts `get_databricks_secret`'s cache; after this
change, only a `DATABRICKS_*` change does.

## `_utilities.py` — full inventory

| Function | Calls (direct) | Change |
|---|---|---|
| `install_brew()` | `check_output` (×1) | add `timeout: float \| None = None`, forward to `check_output` |
| `which_brew()` (`@cache`) | `check_output` (×2), `install_brew()` | add `timeout`, forward to both `check_output` calls and to `install_brew(timeout=timeout)` |
| `which_winget()` (`@cache`) | `check_output` (×1) | add `timeout`, forward to `check_output` |
| *(new)* `get_prefixed_environ(*prefixes)` | — | new helper; see "Cache-key narrowing" above |

## `databricks.py` — full inventory

| Function | Calls (direct) | Change |
|---|---|---|
| `_install_sh_databricks_cli()` | `check_call` (×1) | add `timeout`, forward |
| `_install_databricks_cli()` | `which_winget()`, `which_brew()`, `check_output` (×4), `_install_sh_databricks_cli()` | add `timeout`, forward to all five |
| `which_databricks()` | `check_output` (×1), `_install_databricks_cli()` | add `timeout`, forward to both |
| `_databricks_auth_profiles()` (`@cache`) | `which_databricks()`, `check_output` (×1) | add `timeout`, forward to both |
| `_get_host_profile(host)` (`@cache`) | `_databricks_auth_profiles()` | add `timeout`, forward |
| `_databricks_auth_describe(...)` | `_get_host_profile()`, `which_databricks()`, `check_output` (×2) | complete the partial work above: forward `timeout` on all four calls |
| `_databricks_bundle_summary(target, profile=None)` | `which_databricks()`, `check_output` (×1) | add `timeout`, forward to both |
| `_databricks_auth_login_target(target, **env)` | `_databricks_auth_login()`, `_databricks_bundle_summary()` | add `timeout`, forward to both |
| `_databricks_auth_login(...)` (`@cache` + `@retry`) | `which_databricks()`, `_get_host_profile()`, `check_call` (×2), `_databricks_auth_login_target()`, `_databricks_auth_profiles()`, self (recursive, line ~441) | add `timeout`, forward to all six call sites |
| `databricks_auth_login(...)` | `_databricks_auth_describe()`, `_databricks_auth_login()` | already partially done; finish per cleanup notes above; **also** replace `**os.environ` with `**get_prefixed_environ("DATABRICKS_")` (line ~497) |
| `_get_env_databricks_workspace_client(...)` (`@cache`) | `databricks_auth_login()` (line ~561) | add `timeout`, forward — currently this call site passes `host`/`profile` only |
| `get_databricks_workspace_client(...)` | `_get_env_databricks_workspace_client()` | add `timeout`, forward; **also** replace `**os.environ` with `**get_prefixed_environ("DATABRICKS_")` (line ~680) |
| `get_dbutils(...)` | `get_databricks_workspace_client()` | add `timeout`, forward |
| `_get_secret(...)` (`@cache`) | `get_dbutils()` | add `timeout`, forward |
| `get_databricks_secret(...)` | `_get_secret()` | add `timeout`, forward — this is the main public secret-retrieval entry point; **also** replace `**os.environ` with `**get_prefixed_environ("DATABRICKS_")` (line ~939) |
| `_get_scope_key_secret(scope_key, ...)` | `get_databricks_secret()` | add `timeout`, forward (see decorator note below re: how this actually receives a value) |
| `apply_databricks_secrets_arguments(...)` | builds `partial(_get_scope_key_secret, **asdict(...))` | add `timeout: float \| None = None` field to `DatabricksWorkspaceClientArguments` dataclass so it flows through the existing `asdict(...)` unpack into the `partial` |
| `main()` (CLI) | `_install_databricks_cli()`, `get_databricks_secret()` | add `--timeout FLOAT` argparse option to both the `install` and `get` subcommands, forward to the respective call |

## `onepassword.py` — full inventory

| Function | Calls (direct) | Change |
|---|---|---|
| `_install_op()` | `which_winget()`, `which_brew()`, `check_output` (×2) | add `timeout`, forward to all four |
| `which_op()` | `check_output` (×1), `_install_op()` | add `timeout`, forward to both |
| `_op_signin(account=None)` (`@cache`) | `which_op()`, `check_output` (×1) | add `timeout`, forward to both |
| `iter_op_account_list()` | `which_op()`, `check_output` (×1) | add `timeout`, forward to both |
| `op_signin(account=None)` | `_op_signin()`, `iter_op_account_list()`, `which_op()` | add `timeout`, forward to all three |
| `async_read_onepassword_secret(...)` (`@alru_cache`) | `op_signin()`, `which_op()`, `check_output` (×1) | add `timeout`, forward to all three (the `_async_resolve_resource`/`_async_resolve_connect_resource` branches don't touch `check_output` — no change needed there) |
| `_read_onepassword_secret(...)` (`@cache`) | `op_signin()`, `which_op()`, `check_output` (×1) | add `timeout`, forward to all three |
| `get_onepassword_secret(...)` / `read_onepassword_secret` (alias) | `_read_onepassword_secret()` | add `timeout`, forward — main public secret-retrieval entry point; **also** replace `**os.environ` with `**get_prefixed_environ("OP_")` (line ~397) |
| `apply_onepassword_arguments(...)` | builds `partial(read_onepassword_secret_, ...)` / `partial(async_read_onepassword_secret_, ...)` | add `timeout: float \| None = None` field to `ApplyOnepasswordArgumentsOptions`, thread through the existing conditional-kwargs `partial(...)` construction (same pattern as `account`/`token`/`host`) |
| `main()` (CLI) | `_install_op()`, `read_onepassword_secret()` | add `--timeout FLOAT` argparse option to both the `install` and `get` subcommands, forward to the respective call |

## Out of scope

- `callback.py` / `apply_callback_arguments` itself — no change. It stays
  a single-positional-argument callback contract; decorator-level timeout
  configuration (via the options dataclasses above) is the only path for
  `apply_databricks_secrets_arguments`/`apply_onepassword_arguments`.
- `_async_resolve_resource`, `_async_resolve_connect_resource`,
  `_resolve_connect_resource` (`onepassword.py`) — these use the
  `onepassword-sdk`/`onepasswordconnectsdk` HTTP clients, not
  `check_output`. Any timeout support for them would be a different
  mechanism (HTTP client timeout) and is a separate concern.
- `environment.py`, `defaults.py`, `callback.py`, `errors.py`,
  `utilities.py` — none call `check_output`/`check_call`, directly or
  transitively.

## Testing

Per `docs/contributing.md`, any test exercising a real external resource
(Databricks CLI/workspace, 1Password CLI, Homebrew, WinGet, network
installers) must be a genuine integration test — no mocking those systems.
Reuse the existing `databricks_env`/`onepassword_vault` fixtures.

- `tests/test_subprocess.py`: `check_output`/`check_call` with a very
  small `timeout` against a real long-running command (e.g. `sleep 5` /
  platform equivalent) raises `subprocess.TimeoutExpired`; a generous
  `timeout` against a fast command succeeds normally and returns the same
  result as an untimed call.
- `tests/test__utilities.py`: `which_brew`/`which_winget`/`install_brew`
  accept `timeout` and forward it (assert `TimeoutExpired` with a
  near-zero timeout against the real `--version`/install invocation,
  platform-gated as the existing tests for these already are).
- `tests/test_databricks.py`: `which_databricks`, `_databricks_auth_profiles`,
  `_databricks_auth_describe`, `databricks_auth_login`,
  `get_databricks_secret` each accept `timeout` and a near-zero value
  raises `TimeoutExpired` against the real CLI (`databricks_env` fixture).
  Also assert a generous `timeout` doesn't change the successful result
  compared to the existing untimed tests.
- `tests/test_onepassword.py`: same pattern for `which_op`, `op_signin`,
  `iter_op_account_list`, `get_onepassword_secret`/`read_onepassword_secret`,
  `async_read_onepassword_secret` (`onepassword_vault` fixture).
- `tests/test_databricks.py` / `tests/test_onepassword.py`: confirm
  `apply_databricks_secrets_arguments`/`apply_onepassword_arguments`
  accept a `timeout` on `DatabricksWorkspaceClientArguments`/
  `ApplyOnepasswordArgumentsOptions` and that it actually reaches the
  underlying CLI call (near-zero timeout → the decorated function call
  raises/propagates `TimeoutExpired`, or the resulting
  `ArgumentsResolutionError` wraps it, matching how other callback
  failures already surface through `apply_callback_arguments`).
- Cache-key regression guard: for at least one `@cache`d function in the
  chain (e.g. `_op_signin` or `_databricks_auth_login`), assert that two
  calls with *different* `timeout` values each trigger a real CLI
  round-trip (not a cache hit from the other), while two calls with the
  *same* `timeout` (and otherwise identical arguments) do hit cache —
  parallels the existing wall-clock-timing approach used in
  `docs/superpowers/specs/2026-07-21-missing-test-coverage-design.md` for
  `databricks_auth_login(force=True)`.
- `tests/test__utilities.py`: `get_prefixed_environ` — pure unit test (no
  external resource involved), no mocking restriction applies. Assert it
  returns only matching-prefix entries, supports multiple prefixes, and
  returns an empty dict when nothing matches.
- Cache-key narrowing regression guard: for one narrowed call site (e.g.
  `get_databricks_secret`), assert that changing an *irrelevant* env var
  (e.g. `PATH`) between two otherwise-identical calls still hits cache
  (no fresh CLI/SDK round-trip), while changing a `DATABRICKS_*` var does
  bust it — proves the narrowing didn't accidentally stop invalidating on
  vars that matter, and does skip ones that don't. Same pattern for
  `get_onepassword_secret` with an `OP_*` var.

## Suggested implementation order

1. Finish `subprocess.py` cleanup (overload parameter ordering).
2. `_utilities.py` (leaf functions, no dependents within the library
   other than `databricks.py`/`onepassword.py`), including the new
   `get_prefixed_environ` helper.
3. `databricks.py`, bottom-up: `_install_sh_databricks_cli` →
   `_install_databricks_cli` → `which_databricks` →
   `_databricks_auth_profiles` → `_get_host_profile` →
   `_databricks_auth_describe` (finish) → `_databricks_bundle_summary` →
   `_databricks_auth_login_target` → `_databricks_auth_login` →
   `databricks_auth_login` (finish) → `_get_env_databricks_workspace_client`
   → `get_databricks_workspace_client` → `get_dbutils` → `_get_secret` →
   `get_databricks_secret` → `_get_scope_key_secret` →
   `DatabricksWorkspaceClientArguments`/`apply_databricks_secrets_arguments`
   → CLI `main()`.
4. `onepassword.py`, bottom-up: `_install_op` → `which_op` → `_op_signin`
   → `iter_op_account_list` → `op_signin` →
   `async_read_onepassword_secret`/`_read_onepassword_secret` →
   `get_onepassword_secret`/`read_onepassword_secret` →
   `ApplyOnepasswordArgumentsOptions`/`apply_onepassword_arguments` → CLI
   `main()`.
5. Tests, per module, alongside each step (not deferred to the end) —
   easier to confirm `TimeoutExpired` actually propagates one layer at a
   time than to debug the whole chain after every function has changed.
6. `make format` and `make test` at the end.
