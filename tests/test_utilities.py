from __future__ import annotations

import sys
from subprocess import check_output

from decorative_secrets._utilities import which_op
from decorative_secrets.errors import (
    OnePasswordCommandLineInterfaceNotInstalledError,
)


def test_which_op() -> None:
    """
    Verify that the 1Password CLI is installed on invocation.
    """
    try:
        op: str = which_op()
        assert check_output((op, "--version"))
    except OnePasswordCommandLineInterfaceNotInstalledError:
        if sys.platform.startswith(("darwin", "win32")):
            raise
