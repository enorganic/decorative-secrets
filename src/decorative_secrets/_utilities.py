from __future__ import annotations

import os
import sys
from functools import cache
from shutil import which
from subprocess import (
    DEVNULL,
    PIPE,
    CalledProcessError,
    check_call,
    list2cmdline,
    run,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def check_output(
    args: tuple[str, ...],
    cwd: str | Path = "",
    input: str | bytes | None = None,  # noqa: A002
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
    output: str = run(
        args,
        stdout=PIPE,
        stderr=DEVNULL,
        check=True,
        cwd=cwd or None,
        input=input,
    ).stdout.decode("utf-8", errors="ignore")
    if echo:
        print(output)  # noqa: T201
    return output


def install_brew() -> None:
    """
    Install Homebrew on macOS if not already installed.
    """
    env: dict[str, str] = os.environ.copy()
    env["NONINTERACTIVE"] = "1"
    check_call(
        (
            "/bin/bash -c "
            '"$(curl -fsSL '
            "https://raw.githubusercontent.com"
            '/Homebrew/install/HEAD/install.sh)"'
        ),
        env=env,
        shell=True,  # noqa: S602
    )
    check_call(
        (
            "echo >> /home/runner/.bashrc && "  # noqa: S607
            "echo 'eval \"$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)\"'"
            " >> /home/runner/.bashrc && "
            'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"'
        ),
        shell=True,  # noqa: S602
    )
    check_call(
        (
            "sudo",
            which("apt-get") or "apt-get",
            "install",
            "build-essential",
        ),
        shell=True,  # noqa: S602
    )


@cache
def which_brew() -> str:
    """
    Find the `brew` executable, or install Homebrew if not found.
    """
    brew: str | None
    brew = which("brew") or "brew"
    try:
        check_output((brew, "--version"))
    except (CalledProcessError, FileNotFoundError):
        install_brew()
        brew = which("brew")
        if not brew:
            if sys.platform == "darwin":
                brew = "/opt/homebrew/bin/brew"
                if not os.path.exists(brew):
                    brew = "brew"
            else:
                brew = "/home/linuxbrew/.linuxbrew/bin/brew"
                if not os.path.exists(brew):
                    brew = "brew"
    return brew


def install_op() -> None:
    """
    Install the 1Password CLI.
    """
    if sys.platform.startswith("win"):
        check_output((which("winget") or "winget", "install", "1password-cli"))
    else:  # if sys.platform == "darwin"
        check_output((which_brew(), "install", "1password-cli"))


def which_op() -> str:
    op: str = which("op") or "op"
    try:
        check_output((op, "--version"))
    except (CalledProcessError, FileNotFoundError):
        install_op()
        op = which("op") or "op"
    return op


@cache
def op_signin(account: str | None) -> str:
    """
    Sign in to 1Password using the CLI if not already signed in.
    """
    op: str = which_op()
    if not account:
        account = os.getenv("OP_ACCOUNT")
    check_output(
        (op, "signin", "--account", account) if account else (op, "signin"),
    )
    return op
