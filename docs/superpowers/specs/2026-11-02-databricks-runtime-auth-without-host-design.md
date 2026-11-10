# Runtime authentication when no host is given — design

## Problem

0.14.1 defaults a `WorkspaceClient` to the SDK's `runtime` authentication when
running inside a Databricks Runtime, but only when a `host` is passed
(`if host and ...` in `_get_env_databricks_workspace_client`).

Inside a runtime, the usual call is host-less, e.g.
`get_databricks_secret(scope, key)`. Without `auth_type="runtime"`, the SDK's
default credential chain tries `databricks-cli` before `runtime`. Databricks
Runtime ships a CLI shim which refuses non-interactive use, so the chain
raises instead of falling through:

```
ValueError: default auth: databricks-cli: cannot get access token: The
Databricks CLI is only supported for interactive use from the web terminal.
```

Observed in a `python_wheel_task` on classic compute (DBR 18.1,
`USER_ISOLATION`, no `DATABRICKS_*` authentication environment variables).
Such a task has no `dbutils` in IPython or globals, so `get_dbutils` falls
back to `WorkspaceClient`, which is where the failure occurs.

The 0.14.1 remote test only covered an explicit `host=` on serverless
compute, so it did not exercise this path.

## Approach

A missing host, with no `DATABRICKS_HOST` either, means "the workspace I am
running in". Treat it as the runtime's own workspace.

1. `_is_databricks_runtime_workspace_host` accepts `host: str | None`. For
   `None` it returns `True` when running in a Databricks Runtime and
   `Config(auth_type="runtime")` resolves a host. A host which is set but
   differs from the runtime's workspace still returns `False`.
2. `_get_env_databricks_workspace_client` drops the `host and` precondition and
   passes `host or os.environ.get("DATABRICKS_HOST")` to the helper, which is
   the host the SDK would otherwise use.
3. All other guards are unchanged: no explicit `auth_type`, no explicit
   credentials, no authentication environment variables.

Outside a runtime nothing changes, because `_is_databricks_runtime()`
short-circuits first.

## Matching a host which is written differently

A runtime may report its host differently from how a workspace is usually
addressed (for example a regional URL rather than the workspace's `dbc-*`
URL), so comparing host strings alone rejects a caller's explicit host for the
very workspace the runtime belongs to. When the hosts differ as written,
`_is_databricks_runtime_workspace_host` compares workspace IDs instead:

- The requested host's ID is read from its unauthenticated
  `/.well-known/databricks-config` endpoint (`_get_host_workspace_id`), with an
  explicit timeout. `Config(host=...)` is deliberately not used: constructing
  it also initializes authentication.
- The runtime's ID is read with `WorkspaceClient.get_workspace_id()`, using the
  runtime's own authentication (`_get_config_workspace_id`).
  `Config.workspace_id` is not used: it does not exist in every SDK version
  (it is absent from the SDK on serverless compute), nor is it set by every
  runtime authentication provider.
- Matching host strings short-circuit without any network call, and any
  failure to determine either ID means "not the runtime's workspace", so the
  caller falls back to normal authentication.

## Testing

No mocking of Databricks (see `docs/contributing.md`).

- Local: `_is_databricks_runtime_workspace_host(None)` is `False` outside a
  runtime.
- Local: `_get_host_workspace_id` is `None` for an unreachable host, and for a
  real workspace host equals the ID the SDK resolves, however the host is
  written.
- Remote: extend `tests/is_databricks_runtime_task.py` to assert that
  `get_databricks_workspace_client()` with no arguments authenticates with
  `runtime` and can make a real API call, and that the runtime's workspace ID
  equals the ID advertised by the workspace's own host.

## Known gaps and risks

- The ID comparison is only exercised where the two hosts already match as
  written (serverless compute). A runtime which reports a different host for
  the same workspace is not reproduced by any test.

- The remote test runs on serverless compute only. The observed failure was on
  classic compute, which the test workspace does not permit ("Only serverless
  compute is supported in the workspace"), so the classic path is unverified.
  If `Config(auth_type="runtime")` raised on classic compute, the helper would
  return `False` and the fix would silently do nothing there.
- `get_databricks_secret` with no host needs a readable secret scope in the
  test workspace; if none exists, the remote check is limited to the
  workspace client.
