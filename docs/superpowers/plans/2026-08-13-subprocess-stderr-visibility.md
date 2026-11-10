# Visible `stderr` in `check_output`/`check_call` Failures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `CalledProcessError`s raised by `check_output`/`check_call`
show their captured stderr in `str(error)`, so a default (uncaught)
traceback reveals why a command failed instead of just its exit code —
fixing a diagnostic gap identified while investigating a CI failure in a
downstream consumer of this library.

**Architecture:** A `CalledProcessError` subclass (in `subprocess.py`,
subclassing the stdlib exception) overriding `__str__` to append decoded,
tail-capped stderr. Raised from both branches of `check_output`;
`check_call` inherits the fix automatically since it delegates to
`check_output`. No caller elsewhere in the repo changes.

**Tech Stack:** Pure stdlib `subprocess`/`tempfile`; no new dependencies.

Implements
[docs/superpowers/specs/2026-08-13-subprocess-stderr-visibility-design.md](../specs/2026-08-13-subprocess-stderr-visibility-design.md).

## Global Constraints

- No mocks — all new tests run real commands (`bash`, `sleep`, `echo`), per
  `docs/contributing.md`.
- `error.stderr` must remain `bytes` in the `suppress_stderr=True` path and
  follow `text` mode in the `suppress_stderr=False` path — unchanged from
  today. `databricks.py:457`'s `error.stderr.decode()` and
  `databricks.py:218-224`'s `error.stdout` byte-substring checks must keep
  working untouched.
- The raised exception must remain an instance of stdlib
  `subprocess.CalledProcessError` (via subclassing), so every existing
  `except CalledProcessError` / `with suppress(CalledProcessError)` /
  `@retry(...)` site in `databricks.py`/`onepassword.py` keeps matching.
- `make format` and `make test` must pass after the change.

---

### Task 1: Add the `CalledProcessError` subclass and overload fix

**Files:**
- Modify: `src/decorative_secrets/subprocess.py`

- [ ] **Step 1: Alias the stdlib exception import**

  Change:

  ```python
  from subprocess import (
      PIPE,
      CalledProcessError,
      CompletedProcess,
      run,
  )
  ```

  to:

  ```python
  from subprocess import (
      PIPE,
      CompletedProcess,
      run,
  )
  from subprocess import CalledProcessError as _CalledProcessError
  ```

- [ ] **Step 2: Add the subclass**

  Immediately after the imports (before `get_default_shell`), add:

  ```python
  _STDERR_TAIL_LENGTH: int = 10_000


  class CalledProcessError(_CalledProcessError):
      """
      Identical to `subprocess.CalledProcessError`, except that `str(error)`
      includes the tail end of captured stderr, so a default traceback
      shows the cause of a command's failure instead of just its exit code.
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

- [ ] **Step 3: Raise the subclass in the `suppress_stderr=True` branch**

  Replace (current lines ~159-162):

  ```python
              except CalledProcessError as error:
                  stderr.seek(0)
                  error.stderr = stderr.read().encode("utf-8", errors="ignore")
                  raise
  ```

  with:

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

- [ ] **Step 4: Raise the subclass in the `suppress_stderr=False` branch**

  Wrap the `else:` branch's `run(...)` call (currently lines ~163-174) in a
  `try`/`except`:

  ```python
      else:
          try:
              completed_process = run(
                  args_,
                  capture_output=True,
                  check=True,
                  cwd=cwd or None,
                  input=input,
                  env=env,
                  text=text,
                  shell=shell_,
                  timeout=timeout,
              )
          except _CalledProcessError as error:
              raise CalledProcessError(
                  error.returncode,
                  error.cmd,
                  output=error.output,
                  stderr=error.stderr,
              ) from None
  ```

- [ ] **Step 5: Fix the first `@overload`'s missing `suppress_stderr`**

  Add `suppress_stderr: bool = True` to the `text: Literal[True]` overload
  (currently lines 43-54), matching the other two overloads' parameter
  order (`cwd, input, env, suppress_stderr, shell, timeout, echo`).

- [ ] **Step 6: Run `make format`**

  From the repo root: `make format`
  Expected: `hatch fmt --formatter && hatch fmt --linter && hatch run mypy`
  all pass with no errors.

---

### Task 2: Rewrite and extend `test_subprocess.py`

**Files:**
- Modify: `tests/test_subprocess.py`

- [ ] **Step 1: Replace the broken `test_check_output`**

  Replace the current `test_check_output` (lines 82-103) — whose
  `pytest.raises(AssertionError)` calls are no-ops (never used as a context
  manager) and whose `sys.stderr` swap can't capture a child process's
  fd-level stderr — with:

  ```python
  def test_check_call_suppresses_and_attaches_stderr(
      capfd: pytest.CaptureFixture[str],
  ) -> None:
      """
      `check_call` suppresses a failing command's stderr from the console,
      attaches it to `error.stderr` as bytes, and includes it in
      `str(error)`.
      """
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

  Add `import subprocess` and `CalledProcessError` to the existing
  `from decorative_secrets.subprocess import (...)` block at the top of the
  file (already imports `check_call`, `check_output`, `get_default_shell`,
  `list2cmdline`).

- [ ] **Step 2: Add `test_check_output_error_str_includes_stderr`**

  Same assertion shape, called via `check_output` directly rather than
  through `check_call`, to cover the function the fix actually lives in:

  ```python
  def test_check_output_error_str_includes_stderr() -> None:
      """
      `check_output` includes captured stderr in `str(error)` on failure.
      """
      with pytest.raises(CalledProcessError) as exc_info:
          check_output(("bash", "-c", "echo oops >&2; exit 1"))
      assert "oops" in str(exc_info.value)
  ```

- [ ] **Step 3: Add `test_check_output_unsuppressed_error_str_includes_stderr`**

  Covers the `suppress_stderr=False` branch:

  ```python
  def test_check_output_unsuppressed_error_str_includes_stderr() -> None:
      """
      With `suppress_stderr=False`, a failing command's stderr is still
      included in `str(error)`.
      """
      with pytest.raises(CalledProcessError) as exc_info:
          check_output(
              ("bash", "-c", "echo oops >&2; exit 1"),
              suppress_stderr=False,
          )
      assert "oops" in str(exc_info.value)
  ```

- [ ] **Step 4: Add `test_called_process_error_str_truncates_long_stderr`**

  ```python
  def test_called_process_error_str_truncates_long_stderr() -> None:
      """
      `str(error)` truncates stderr longer than the tail-length cap,
      keeping only the end of the output (where the actionable error
      usually is) and marking the truncation.
      """
      with pytest.raises(CalledProcessError) as exc_info:
          check_output(
              ("bash", "-c", "yes error-line | head -c 20000 >&2; exit 1")
          )
      message: str = str(exc_info.value)
      assert "..." in message
      assert len(message) < 15_000  # noqa: PLR2004
  ```

- [ ] **Step 5: Confirm the bytes-stdout contract is unchanged**

  Verify (add a test if not already covered by existing ones) that
  `check_output(..., text=False)` failures still populate `error.output` as
  bytes — this plan does not touch `.output`/`.stdout` handling, but the
  test suite should assert it explicitly given the raise sites were
  rewritten.

- [ ] **Step 6: Run `make test`**

  From the repo root: `make test`
  Expected: `hatch fmt --check && hatch run mypy && hatch test -c` all pass,
  coverage `fail_under = 80` satisfied.

---

### Task 3: Release

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump the version**

  Change `version = "0.13.3"` to `version = "0.14.0"` (minor —
  behavior-compatible, additive).

- [ ] **Step 2: Confirm `make format && make test` pass at the bumped version**

- [ ] **Step 3: Release (user-approved)**

  Per repo convention (`make distribute` runs `hatch build && hatch
  publish`) — not run as part of this plan without separate explicit
  permission. Once published, downstream consumers pinned with a
  compatible-release specifier (e.g. `~=0.12`) pick up 0.14.0 automatically
  on their next fresh environment resolution; no other action is required
  from this repo.
