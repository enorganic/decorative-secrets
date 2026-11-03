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

## Testing

No mocking of Databricks (see `docs/contributing.md`).

- Local: `_is_databricks_runtime_workspace_host(None)` is `False` outside a
  runtime.
- Remote: extend `tests/is_databricks_runtime_task.py` to assert that
  `get_databricks_workspace_client()` with no arguments authenticates with
  `runtime` and can make a real API call.
- Classic compute: parametrize `test_is_databricks_runtime` over serverless
  and a classic `new_cluster` run, using a script task rather than a notebook.
  This is the configuration which failed. If `Config(auth_type="runtime")`
  raised there, the helper would return `False` and the fix would silently do
  nothing, so only a classic run can prove it.

## Known gaps and risks

- A classic run needs a cluster to start: slower (several minutes) and more
  expensive than serverless, multiplied across the CI matrix.
- The identity running the test needs permission to create job clusters, which
  has not been verified for the CI service principal.
- `get_databricks_secret` with no host needs a readable secret scope in the
  test workspace; if none exists, the remote check is limited to the
  workspace client.
