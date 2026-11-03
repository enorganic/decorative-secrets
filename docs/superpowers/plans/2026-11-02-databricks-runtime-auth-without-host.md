# Runtime authentication when no host is given — implementation plan

See the [design](../specs/2026-11-02-databricks-runtime-auth-without-host-design.md).

1. Change `_is_databricks_runtime_workspace_host` in
   `src/decorative_secrets/databricks.py` to accept `host: str | None`; `None`
   means the runtime's own workspace.
2. In `_get_env_databricks_workspace_client`, remove the `host and`
   precondition and pass `host or os.environ.get("DATABRICKS_HOST")` to the
   helper.
3. Add a local test to `tests/test_databricks.py`:
   `_is_databricks_runtime_workspace_host(None)` is `False` outside a runtime
   (extend the existing parametrized tests where possible).
4. Extend `tests/is_databricks_runtime_task.py`: a host-less
   `get_databricks_workspace_client()` authenticates with `runtime` and
   `current_user.me()` succeeds; optionally a host-less
   `get_databricks_secret` if a readable test scope exists.
5. Bump `pyproject.toml` to 0.14.2.
6. Verify: `hatch test -k is_databricks_runtime`, then `make format` and
   `make test`.
