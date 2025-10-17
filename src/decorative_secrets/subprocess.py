from __future__ import annotations

from subprocess import DEVNULL, PIPE, list2cmdline, run
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def check_output(
    args: tuple[str, ...],
    cwd: str | Path = "",
    input: str | bytes | None = None,  # noqa: A002
    env: Mapping[str, str] | None = None,
    *,
    echo: bool = False,
) -> str:
    """
    This function mimics `subprocess.check_output`, but redirects stderr
    to DEVNULL, and ignores unicode decoding errors.

    Parameters:

    - command (tuple[str, ...]): The command to run
    """
    if echo:
        if cwd:
            print("$", "cd", cwd, "&&", list2cmdline(args))  # noqa: T201
        else:
            print("$", list2cmdline(args))  # noqa: T201
    output: str = (
        run(
            args,
            stdout=PIPE,
            stderr=DEVNULL,
            check=True,
            cwd=cwd or None,
            input=input,
            env=env,
        )
        .stdout.rstrip()
        .decode("utf-8", errors="ignore")
    )
    if echo:
        print(output)  # noqa: T201
    return output
