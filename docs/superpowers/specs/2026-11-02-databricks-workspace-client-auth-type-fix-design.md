# `is_databricks_runtime` integration test — design

## Goal

Verify `decorative_secrets.databricks.is_databricks_runtime()` against a real
Databricks Runtime, with no mocks and no faked environment.

## Approach

`tests/test_databricks.py::test_is_databricks_runtime`:

1. Asserts the local test runner is *not* a Databricks Runtime (negative
   baseline, nothing patched).
2. Builds a wheel of the working tree (the function is unreleased, so the
   published package can't be used) with `hatch run python -m pip wheel
   --no-deps`.
3. Uploads the wheel and `tests/is_databricks_runtime_task.py` to a unique
   directory under the caller's `/Workspace/Users/<user>/` folder.
4. Submits a one-time serverless job run (`jobs.submit`) whose environment
   installs the wheel and runs the script.
5. The script raises unless `is_databricks_runtime()` is `True` on the driver
   and inside a Spark UDF (the worker path).
6. The test asserts the run succeeded, surfaces the remote error/trace on
   failure, and always deletes the uploaded directory.

## Known gaps and risks

- Serverless compute only. The classic-compute driver
  (`DATABRICKS_RUNTIME_VERSION`), classic executor (`DBR_VERSION`) and DBR 19
  standard `sys.prefix` branches would require a `new_cluster` run.
- The identity running the test needs permission to submit serverless job runs
  and to write to its own workspace folder. This has not been verified for the
  CI service principal.
- Slow (roughly 2–5 minutes per run), multiplied across the CI matrix.
- A workspace-level block on triggering new runs (observed once as
  "Triggering new runs for organization ... is currently disabled
  temporarily") fails the test for reasons unrelated to the code under test.
