"""
This script is executed *on Databricks compute* (not locally) by
`tests/test_databricks.py::test_is_databricks_runtime`. It is intentionally
not named `test_*`, so pytest does not collect it.

It fails (non-zero exit, visible in the run output) unless
`is_databricks_runtime()` returns `True` on both the driver and the workers,
and unless a workspace client created with an explicit host, or with no host
at all (and no `auth_type`), authenticates with the runtime identity, while
credentials which are explicitly supplied still take precedence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql import SparkSession
from pyspark.sql.functions import udf

from decorative_secrets.databricks import (
    _is_databricks_runtime,
    _is_databricks_runtime_workspace_host,
    get_databricks_workspace_client,
)

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient


@udf("boolean")
def _is_databricks_runtime_on_worker(_: int) -> bool:
    # Imported inside the function so the import happens on the worker,
    # rather than depending on how this script's globals are pickled
    from decorative_secrets.databricks import (  # noqa: PLC0415
        _is_databricks_runtime,
    )

    return _is_databricks_runtime()


def _check_hostless_client() -> None:
    """
    No host at all means the runtime's own workspace, so a workspace client
    must default to runtime authentication then too (the SDK's default chain
    would otherwise reach the Databricks CLI shim, which refuses
    non-interactive use), and work for a real API call.
    """
    message: str
    if not _is_databricks_runtime_workspace_host(None):
        message = "No host was not recognized as the runtime workspace"
        raise RuntimeError(message)
    client: WorkspaceClient = get_databricks_workspace_client()
    if client.config.auth_type != "runtime":
        message = (
            "Expected runtime auth without a host, "
            f"got {client.config.auth_type!r}"
        )
        raise RuntimeError(message)
    if not client.current_user.me().user_name:
        message = "The host-less runtime-authenticated client has no user name"
        raise RuntimeError(message)


def main() -> None:
    message: str
    if not _is_databricks_runtime():
        message = "is_databricks_runtime() was False on the driver"
        raise RuntimeError(message)
    spark: SparkSession = SparkSession.builder.getOrCreate()
    if not all(
        bool(row[0])
        for row in spark.range(2)
        .select(_is_databricks_runtime_on_worker("id"))
        .collect()
    ):
        message = "is_databricks_runtime() was False on a worker"
        raise RuntimeError(message)
    host: str = f"https://{spark.conf.get('spark.databricks.workspaceUrl')}"
    # Runtime authentication is only for the runtime's own workspace
    # (however its host is written), never for another workspace
    other_host: str = "https://other-workspace.cloud.databricks.com"
    if not (
        _is_databricks_runtime_workspace_host(host)
        and _is_databricks_runtime_workspace_host(f"{host}/")
        and _is_databricks_runtime_workspace_host(
            host.removeprefix("https://").upper()
        )
    ):
        message = f"{host!r} was not recognized as the runtime workspace"
        raise RuntimeError(message)
    if _is_databricks_runtime_workspace_host(other_host):
        message = f"{other_host!r} was wrongly treated as the runtime host"
        raise RuntimeError(message)
    # An explicit host, with nothing else selecting an authentication
    # method, defaults to runtime authentication...
    client: WorkspaceClient = get_databricks_workspace_client(host=host)
    if client.config.auth_type != "runtime":
        message = f"Expected runtime auth, got {client.config.auth_type!r}"
        raise RuntimeError(message)
    # ...and works for a real API call
    if not client.current_user.me().user_name:
        message = "The runtime-authenticated client has no user name"
        raise RuntimeError(message)
    _check_hostless_client()
    # Explicitly supplied credentials are respected, not overridden
    # (a placeholder value: the client is never used to make a request)
    token_client: WorkspaceClient = get_databricks_workspace_client(
        host=host,
        token="placeholder-token",
    )
    if token_client.config.auth_type != "pat":
        message = f"Expected token auth, got {token_client.config.auth_type!r}"
        raise RuntimeError(message)


if __name__ == "__main__":
    main()
