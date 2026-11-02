# `is_databricks_runtime` integration test — implementation plan

See the [design](../specs/2026-11-02-databricks-workspace-client-auth-type-fix-design.md).

1. Add `tests/is_databricks_runtime_task.py` (remote script: driver + UDF
   checks, raises `RuntimeError` on failure).
2. Add `test_is_databricks_runtime` to `tests/test_databricks.py`:
   local negative baseline, wheel build, workspace upload, `jobs.submit` on
   serverless, result/error assertions, cleanup in `finally`.
3. Verify: `hatch test -k test_is_databricks_runtime`, then a one-off
   inverted-assertion run to confirm the failure path shows the remote trace,
   then `make format` and `make test`.
