from __future__ import annotations

from subprocess import DEVNULL, PIPE, CompletedProcess, list2cmdline, run
from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


@overload
def check_output(
    args: tuple[str, ...],
    *,
    text: Literal[True] = True,
    cwd: str | Path | None = None,
    input: str | bytes | None = None,  # noqa: A002
    env: Mapping[str, str] | None = None,
    echo: bool = False,
) -> str: ...


@overload
def check_output(
    args: tuple[str, ...],
    *,
    text: Literal[False] = False,
    cwd: str | Path | None = None,
    input: str | bytes | None = None,  # noqa: A002
    env: Mapping[str, str] | None = None,
    echo: bool = False,
) -> bytes: ...


@overload
def check_output(
    args: tuple[str, ...],
    *,
    text: None = None,
    cwd: str | Path | None = None,
    input: str | bytes | None = None,  # noqa: A002
    env: Mapping[str, str] | None = None,
    echo: bool = False,
) -> bytes: ...


def check_output(
    args: tuple[str, ...],
    *,
    text: bool | None = True,
    cwd: str | Path | None = None,
    input: str | bytes | None = None,  # noqa: A002
    env: Mapping[str, str] | None = None,
    echo: bool = False,
) -> str | bytes | None:
    """
    This function mimics `subprocess.check_output`, but redirects stderr
    to DEVNULL, ignores unicode decoding errors, and outputs text by default.

    Parameters:
        args: The command to run
        text: Whether to return output as text (default: `True`). If
            `None`—returns `None`. If `False`, returns the output as
            `bytes`.
        cwd: The working directory to run the command in
        input: Input to send to the command
        env: Environment variables to set for the command
        echo: Whether to print the command and its output (default: False)
    """
    if echo:
        if cwd:
            print("$", "cd", cwd, "&&", list2cmdline(args))  # noqa: T201
        else:
            print("$", list2cmdline(args))  # noqa: T201
    completed_process: CompletedProcess = run(
        args,
        stdout=PIPE,
        stderr=DEVNULL,
        check=True,
        cwd=cwd or None,
        input=input,
        env=env,
        text=text,
    )
    output: str | bytes | None = (
        (None)
        if text is None
        else (
            # str
            completed_process.stdout.rstrip().decode("utf-8", errors="ignore")
        )
        if text
        # bytes
        else (completed_process.stdout.rstrip())
    )
    if echo and (output is not None):
        print(output)  # noqa: T201
    return output


def check_call(
    args: tuple[str, ...],
    *,
    cwd: str | Path | None = None,
    input: str | bytes | None = None,  # noqa: A002
    env: Mapping[str, str] | None = None,
    echo: bool = False,
) -> None:
    """
    This function mimics `subprocess.check_call`, but redirects stderr
    to DEVNULL.

    Parameters:
        args: The command to run
        text: Whether to return output as text (default: `True`). If
            `None`—returns `None`. If `False`, returns the output as
            `bytes`.
        cwd: The working directory to run the command in
        input: Input to send to the command
        env: Environment variables to set for the command
        echo: Whether to print the command and its output (default: False)
    """
    check_output(
        args,
        text=None,
        cwd=cwd,
        input=input,
        env=env,
        echo=echo,
    )
