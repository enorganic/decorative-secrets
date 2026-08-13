# Visible `stderr` in `check_output`/`check_call` Failures — Design

- **Ticket:** none — ad hoc, discovered while diagnosing a CI failure in a
  downstream consumer of this library
- **Date:** 2026-08-13

## Problem

`check_output` in `src/decorative_secrets/subprocess.py` defaults to
`suppress_stderr=True`: the child process's stderr is redirected to a
`TemporaryFile`, and on failure the captured bytes are attached to
`error.stderr` before the `CalledProcessError` is re-raised (lines 144-162).
`check_call` (lines 191-235) delegates entirely to `check_output`, so it
inherits the same behavior. In neither branch does anything print or fold
that captured stderr into the exception's own message — `error.stderr` sits
on the exception object, but `CalledProcessError.__str__` only reports the
command and exit code.

This is invisible in normal use, where a caller catches the exception and
inspects `error.stderr` directly (as `databricks.py:457` already does). It
becomes a real diagnostic problem for any caller that instead lets the
exception propagate to a default traceback — a pattern common in scripts
that call `check_output`/`check_call` uncaught and rely on whatever prints
the traceback (a CI log, a terminal) to explain the failure. In that case
the log shows only, for example:

```
subprocess.CalledProcessError: Command '(...)' returned non-zero exit status 1.
```

with no indication of *why* the command failed — the underlying stderr
existed on the exception the whole time, it just never reached anywhere a
human could see it, forcing the failure to be reconstructed by local
reproduction instead of read off the log.

## Scope

In scope:

1. A `CalledProcessError` subclass in `subprocess.py` whose `__str__`
   appends captured stderr (decoded, tail-capped) to the standard
   command/exit-code message, so any default traceback — not just callers
   that explicitly inspect `.stderr` — shows the cause of a failure.
2. Raising that subclass from both branches of `check_output`
   (`suppress_stderr=True` and `suppress_stderr=False`).
3. Fixing the pre-existing `suppress_stderr` omission on the first
   `@overload` of `check_output`.
4. Rewriting `test_check_output` (lines 82-103), whose current
   `pytest.raises(AssertionError)` calls are no-ops (never used as a context
   manager) and whose `sys.stderr` swap cannot capture a child process's
   fd-level stderr in the first place — it currently verifies nothing.
5. A minor version release (0.13.3 to 0.14.0).

Out of scope:

- Changing `error.stderr`'s type or the `suppress_stderr=True` capture
  mechanism itself (temp file, bytes encoding) — only what happens to that
  data once a `CalledProcessError` is raised.
- `TimeoutExpired` — its stdlib message already states the command and
  timeout value; this design does not touch the timeout path.
- Any change to callers in `databricks.py`/`onepassword.py`/`_utilities.py`.
  They already work today (several inspect `.stderr`/`.stdout` directly,
  or wrap/suppress the exception); a subclass preserves every one of those
  call sites unchanged. See "Compatibility" below.

**Accepted trade-off:** a caller that already prints or logs
`error.stderr` after catching the exception (none currently do, but future
callers might) will see stderr twice — once from `str(error)` in whatever
default logging captured the exception, once from its own explicit
handling. This is a cosmetic duplication, not a correctness issue, and is
preferable to the status quo where the default path shows nothing.

## Design

### `CalledProcessError` subclass

Added to `subprocess.py`. The stdlib import is aliased so the module can
still shadow the name `CalledProcessError` for its own callers, consistent
with how this module already shadows `check_output`/`check_call`/
`list2cmdline` relative to their stdlib counterparts:

```python
from subprocess import CalledProcessError as _CalledProcessError

_STDERR_TAIL_LENGTH: int = 10_000


class CalledProcessError(_CalledProcessError):
    """
    Identical to `subprocess.CalledProcessError`, except that `str(error)`
    includes the tail end of captured stderr, so a default traceback shows
    the cause of a command's failure instead of just its exit code.
    """

    def __str__(self) -> str:
        message: str = super().__str__()
        stderr: str | bytes | None = self.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="ignore")
        stderr = (stderr or "").strip()
        if stderr:
            if len(stderr) > _STDERR_TAIL_LENGTH:
                stderr = f"...{stderr[-_STDERR_TAIL_LENGTH:]}"
            message = f"{message} Stderr:\n{stderr}"
        return message
```

No `__init__` override — the stdlib signature (`returncode, cmd,
output=None, stderr=None`) is kept as-is, so `repr()` and pickling behave
identically to `subprocess.CalledProcessError`.

Tail-capped at 10,000 characters (module constant, easy to retune) because
the actionable error from a failing `pip`/`uv`/`hatch` invocation is
consistently at the *end* of its stderr, not the start; a full dump could
run to thousands of lines for a dependency-resolution failure.

### Raise sites in `check_output`

Both branches construct the new subclass from the caught stdlib exception
and re-raise, rather than mutating the caught instance's class:

`suppress_stderr=True` branch (replaces the current mutate-and-reraise):

```python
            except _CalledProcessError as error:
                stderr.seek(0)
                raise CalledProcessError(
                    error.returncode,
                    error.cmd,
                    output=error.output,
                    stderr=stderr.read().encode("utf-8", errors="ignore"),
                ) from None
```

`suppress_stderr=False` branch (currently has no `except` at all — `run(...,
capture_output=True, check=True, ...)` raises directly): wrap it the same
way, re-raising `CalledProcessError(error.returncode, error.cmd,
output=error.output, stderr=error.stderr) from None`. In this branch
`error.stderr` follows `text` mode (`str` or `bytes`); `__str__` already
handles both.

`raise ... from None` suppresses the "During handling of the above
exception..." chain — the raise site is the same frame as the original
catch, so nothing diagnostic is lost, and the traceback stays as clean as
today's.

`check_call` needs no changes beyond what `check_output` already gives it,
since it delegates entirely.

### Overload fix

While editing, add the missing `suppress_stderr: bool = True` parameter to
the first `@overload` (`text: Literal[True]`, currently lines 43-54) —
the other two overloads and the implementation already have it; this one
was simply missed.

## Compatibility

Confirmed against every in-repo caller of `check_output`/`check_call`:

- `databricks.py:218-224` checks `error.stdout` (bytes substring) — `.stdout`
  is untouched by this change.
- `databricks.py:455-457` does `error.stderr.decode()` — `.stderr` remains
  `bytes` in the `suppress_stderr=True` path, unchanged.
- `databricks.py:239, 243, 257, 261, 412` and similar in `onepassword.py`
  use `with suppress(CalledProcessError)` against the *stdlib* name — since
  the new class subclasses `_CalledProcessError`, `isinstance` checks and
  `except CalledProcessError` clauses written against the stdlib type
  continue to match.
- The `@retry` decorator on `_databricks_auth_login` (`databricks.py:424`)
  matches on `(CalledProcessError,)` — same reasoning, still matches.

No caller needs to change.

## Testing

Per `docs/contributing.md`: real commands, no mocking. All in
`tests/test_subprocess.py`.

1. **Rewrite `test_check_output`** (lines 82-103): replace the broken
   `sys.stderr`-swap-plus-no-op-`pytest.raises` pattern with `capfd` (which
   captures actual OS-level file descriptors, unlike the `StringIO` swap)
   and `pytest.raises` used correctly as a context manager:

   ```python
   def test_check_call_suppresses_and_attaches_stderr(
       capfd: pytest.CaptureFixture[str],
   ) -> None:
       with pytest.raises(CalledProcessError) as exc_info:
           check_call(("bash", "-c", "echo oops >&2; exit 3"))
       assert capfd.readouterr().err == ""
       error: CalledProcessError = exc_info.value
       assert isinstance(error, subprocess.CalledProcessError)
       assert isinstance(error.stderr, bytes)
       assert b"oops" in error.stderr
       assert error.returncode == 3  # noqa: PLR2004
       assert "oops" in str(error)
   ```

2. `test_check_output_error_str_includes_stderr` — same shape via
   `check_output` directly, covering the function `check_call` delegates to.
3. `test_check_output_unsuppressed_error_str_includes_stderr` —
   `suppress_stderr=False` branch; assert `"oops" in str(error)`.
4. `test_called_process_error_str_truncates_long_stderr` — a command
   producing more than `_STDERR_TAIL_LENGTH` characters of stderr (e.g.
   `("bash", "-c", "yes error-line | head -c 20000 >&2; exit 1")`); assert
   `str(error)` contains `"..."` and its length is bounded.
5. Confirm the existing bytes-stdout contract (`check_output(...,
   text=False)` failure) still holds — `error.output` semantics are
   untouched by this change.

## Success criteria

- `str(error)` for a failed `check_output`/`check_call` call includes the
  command's captured stderr (tail-capped), with no caller changes required
  elsewhere in this repo.
- `error.stderr`/`error.stdout` types and values are unchanged from today.
- `make format && make test` pass, including the rewritten
  `test_check_output` and the new tests above.
- Version bumped to `0.14.0` in `pyproject.toml`.
