from __future__ import annotations

from types import ModuleType, SimpleNamespace

import pytest

from decorative_secrets import __main__
from decorative_secrets.__main__ import _get_command, _print_help, main


def test_get_command_normalizes_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `_get_command` pops the first argument, lowercases it, and replaces
    hyphens with underscores (so `--help` becomes `__help`).
    """
    monkeypatch.setattr(__main__.sys, "argv", ["decorative-secrets", "--Help"])
    assert _get_command() == "__help"
    # The consumed argument is removed from `argv`.
    assert __main__.sys.argv == ["decorative-secrets"]


def test_get_command_no_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    With no sub-command argument, `_get_command` returns an empty string.
    """
    monkeypatch.setattr(__main__.sys, "argv", ["decorative-secrets"])
    assert _get_command() == ""


def test_print_help(capsys: pytest.CaptureFixture[str]) -> None:
    """
    `_print_help` prints usage listing the supported secret managers.
    """
    _print_help()
    captured = capsys.readouterr()
    assert "Usage:" in captured.out
    assert "databricks" in captured.out
    assert "onepassword" in captured.out


@pytest.mark.parametrize("help_flag", ["--help", "-h"])
def test_main_help(
    help_flag: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Invoking with a help flag prints usage and does not attempt any import.
    """

    def fail_import(_name: str) -> ModuleType:
        message = "import_module should not be called for the help command"
        raise AssertionError(message)

    monkeypatch.setattr(
        __main__.sys, "argv", ["decorative-secrets", help_flag]
    )
    monkeypatch.setattr(__main__, "import_module", fail_import)
    main()
    assert "Usage:" in capsys.readouterr().out


def test_main_dispatches_to_submodule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A recognized sub-command resolves to a sub-module's `main` function,
    which `main` then invokes.
    """
    called: list[str] = []
    module = SimpleNamespace(main=lambda: called.append("ran"))

    def fake_import(_name: str) -> ModuleType:
        # The first lookup targets `<command>.__main__`; accept it directly.
        return module  # type: ignore[return-value]

    monkeypatch.setattr(
        __main__.sys, "argv", ["decorative-secrets", "databricks"]
    )
    monkeypatch.setattr(__main__, "import_module", fake_import)
    main()
    assert called == ["ran"]


def test_main_falls_back_to_module_without_main_submodule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When `<command>.__main__` is not importable, `main` falls back to
    importing `<command>` itself before calling its `main`.
    """
    attempted: list[str] = []
    called: list[str] = []
    module = SimpleNamespace(main=lambda: called.append("ran"))

    def fake_import(name: str) -> ModuleType:
        attempted.append(name)
        if name.endswith(".__main__"):
            message = "no __main__ submodule"
            raise ImportError(message)
        return module  # type: ignore[return-value]

    monkeypatch.setattr(
        __main__.sys, "argv", ["decorative-secrets", "onepassword"]
    )
    monkeypatch.setattr(__main__, "import_module", fake_import)
    main()
    assert called == ["ran"]
    assert attempted == [
        "decorative_secrets.onepassword.__main__",
        "decorative_secrets.onepassword",
    ]


def test_main_unknown_command_prints_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    An unresolvable sub-command prints the captured traceback followed by
    the usage help, rather than raising.
    """

    def always_fail(name: str) -> ModuleType:
        message = f"no module named {name}"
        raise ImportError(message)

    monkeypatch.setattr(
        __main__.sys, "argv", ["decorative-secrets", "nonsense"]
    )
    monkeypatch.setattr(__main__, "import_module", always_fail)
    main()
    output = capsys.readouterr().out
    assert "Usage:" in output
    assert "ImportError" in output


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
