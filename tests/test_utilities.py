from subprocess import check_output

from decorative_secrets._utilities import which_op


def test_which_op() -> None:
    """
    Verify that the 1Password CLI is installed on invocation.
    """
    op: str = which_op()
    assert check_output((op, "--version"))
