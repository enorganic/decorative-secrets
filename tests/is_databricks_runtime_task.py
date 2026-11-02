"""
This script is executed *on Databricks compute* (not locally) by
`tests/test_databricks.py::test_is_databricks_runtime`. It is intentionally
not named `test_*`, so pytest does not collect it.

It fails (non-zero exit, visible in the run output) unless
`is_databricks_runtime()` returns `True` on both the driver and the workers.
"""

from __future__ import annotations

from pyspark.sql import SparkSession
from pyspark.sql.functions import udf

from decorative_secrets.databricks import is_databricks_runtime


@udf("boolean")
def _is_databricks_runtime_on_worker(_: int) -> bool:
    from decorative_secrets.databricks import is_databricks_runtime

    return is_databricks_runtime()


def main() -> None:
    message: str
    if not is_databricks_runtime():
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


if __name__ == "__main__":
    main()
