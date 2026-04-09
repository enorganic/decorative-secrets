from __future__ import annotations

from subprocess import (
    PIPE,
    CalledProcessError,
    CompletedProcess,
    run,
)
from subprocess import (
    list2cmdline as _list2cmdline,
)
from tempfile import TemporaryFile
from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path


def get_default_shell() -> str | None:
    return None  # os.getenv("SHELL") or os.getenv("COMSPEC")


def list2cmdline(args: Iterable[str], shell: str | None = None) -> str:
    """
    This function is a wrapper around `subprocess.list2cmdline` which ensures
    that arguments containing `[` are properly quoted, making it safe to
    use with `zsh`.
    """
    shell_: str | None = shell or get_default_shell()
    if (not shell_) or (not shell_.lower().endswith("zsh")):
        return _list2cmdline(args)
    return _list2cmdline(
        (
            f"'{arg}'"
            if "[" in arg and not (arg.startswith("'") and arg.endswith("'"))
            else arg
        )
        for arg in args
    )


@overload
def check_output(
    args: tuple[str, ...] | str,
    *,
    text: Literal[True] = True,
    cwd: str | Path | None = None,
    input: str | bytes | None = None,
    env: Mapping[str, str] | None = None,
    shell: bool = False,
    echo: bool = False,
) -> str: ...


@overload
def check_output(
    args: tuple[str, ...] | str,
    *,
    text: Literal[False] = False,
    cwd: str | Path | None = None,
    input: str | bytes | None = None,
    env: Mapping[str, str] | None = None,
    suppress_stderr: bool = True,
    shell: bool = False,
    echo: bool = False,
) -> bytes: ...


@overload
def check_output(
    args: tuple[str, ...] | str,
    *,
    text: None = None,
    cwd: str | Path | None = None,
    input: str | bytes | None = None,
    env: Mapping[str, str] | None = None,
    suppress_stderr: bool = True,
    shell: bool = False,
    echo: bool = False,
) -> bytes: ...


def check_output(  # noqa: C901
    args: tuple[str, ...] | str,
    *,
    text: bool | None = True,
    cwd: str | Path | None = None,
    input: str | bytes | None = None,  # noqa: A002
    env: Mapping[str, str] | None = None,
    suppress_stderr: bool = True,
    shell: bool = False,
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
        suppress_stderr: Whether to prevent stderr from being printed to the
            console
    """
    default_shell: str | None = get_default_shell() if shell else None
    args_: tuple[str, ...] | str = (
        args
        if isinstance(args, str)
        else list2cmdline(args)
        if (shell and not default_shell)
        else (default_shell, list2cmdline(args))
        if default_shell
        and default_shell.endswith(("pwsh.exe", "powershell.exe"))
        else (default_shell, "/c", list2cmdline(args))
        if default_shell and default_shell.endswith("cmd.exe")
        else (default_shell, "-i", "-c", list2cmdline(args))
        if default_shell
        else args
    )
    shell_: bool = shell and ((not default_shell) or (isinstance(args, str)))
    if echo:
        if cwd:
            print("$", "cd", cwd, "&&", list2cmdline(args))  # noqa: T201
        else:
            print("$", list2cmdline(args))  # noqa: T201
    if isinstance(input, bytes) and text:
        input = input.decode("utf-8", errors="ignore")  # noqa: A001
    completed_process: CompletedProcess
    if suppress_stderr:
        with TemporaryFile("w+") as stderr:
            try:
                completed_process = run(
                    args_,
                    stdout=PIPE,
                    stderr=stderr,  # DEVNULL,
                    check=True,
                    cwd=cwd or None,
                    input=input,
                    env=env,
                    text=text,
                    shell=shell_,
                )
            except CalledProcessError as error:
                stderr.seek(0)
                error.stderr = stderr.read().encode("utf-8", errors="ignore")
                raise
    else:
        completed_process = run(
            args_,
            capture_output=True,
            check=True,
            cwd=cwd or None,
            input=input,
            env=env,
            text=text,
            shell=shell_,
        )
    output: str | bytes | None = None
    if text is None:
        pass
    elif text:
        output = completed_process.stdout.rstrip()
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="ignore")
    else:
        output = completed_process.stdout.rstrip()
        if isinstance(output, str):
            output = output.encode("utf-8", errors="ignore")
    if echo and (output is not None):
        print(output)  # noqa: T201
    return output


def check_call(
    args: tuple[str, ...] | str,
    *,
    cwd: str | Path | None = None,
    input: str | bytes | None = None,  # noqa: A002
    env: Mapping[str, str] | None = None,
    suppress_stderr: bool = True,
    shell: bool = False,
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
        shell: Whether to run the command in a shell
        suppress_stderr: Whether to prevent stderr from being printed to the
            console
    """
    check_output(
        args,
        text=None,
        cwd=cwd,
        input=input,
        env=env,
        suppress_stderr=suppress_stderr,
        shell=shell,
        echo=echo,
    )
