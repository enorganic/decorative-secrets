# Timeout Decorator — Design

**Date:** 2026-06-24
**File touched:** `src/decorative_secrets/utilities.py` (+ `tests/test_utilities.py`)

## Goal

Add a `timeout` decorator to `decorative_secrets.utilities` that enforces a
maximum execution time on both synchronous and asynchronous functions. On
expiry it raises the built-in `TimeoutError`.

## Public API

A decorator factory following the existing `retry` / `as_str` pattern:

```python
def timeout(seconds: float) -> Callable[[Callable], Callable]: ...
```

Usage:

```python
@timeout(5)
def slow_lookup() -> str: ...


@timeout(2.5)
async def slow_async_lookup() -> str: ...
```

The returned `decorating_function` branches on `iscoroutinefunction(function)`
(the module's existing helper, which unwraps `partial` and detects async),
exactly like the other decorators in this module.

`seconds` is validated at decoration time: `seconds <= 0` raises `ValueError`.

## Execution strategies

Selected per call:

| Case | Mechanism | True cancellation? |
|------|-----------|--------------------|
| async function | `asyncio.wait_for(coro, seconds)` | Yes — coroutine is cancelled |
| sync, `SIGALRM` available **and** on main thread | `signal.setitimer` + `SIGALRM` handler | Yes — interrupts in place |
| sync, otherwise (Windows, or non-main thread) | `ThreadPoolExecutor(max_workers=1)` + `future.result(timeout=…)` | No — orphan thread runs to completion |

Key constraint driving the design: `signal.SIGALRM` can only be armed from the
main thread of the main interpreter. The check is therefore
`hasattr(signal, "SIGALRM") and threading.current_thread() is
threading.main_thread()`; otherwise we fall back to the thread pool even on
Unix.

The thread-pool fallback cannot kill a running function — on timeout we raise
`TimeoutError` and the worker thread continues to completion (an "orphan"
thread). This matches the SIGALRM caveat that a function "may not stop" and is
the chosen, documented behavior.

## Implementation detail

### Async (`asyncio.wait_for`)

```python
@wraps(function)
async def wrapper(*args, **kwargs):
    try:
        return await asyncio.wait_for(
            function(*args, **kwargs), timeout=seconds
        )
    except asyncio.TimeoutError:
        raise TimeoutError(message) from None
```

On 3.10 `asyncio.wait_for` raises `asyncio.TimeoutError` (a distinct class); on
3.11+ that name aliases the built-in `TimeoutError`. Catching
`asyncio.TimeoutError` and re-raising a clean built-in `TimeoutError`
normalizes message and behavior across versions.

### Sync — SIGALRM path

```python
def _handler(signum, frame):
    raise TimeoutError(message)

old_handler = signal.signal(signal.SIGALRM, _handler)
signal.setitimer(signal.ITIMER_REAL, seconds)  # float-friendly
try:
    return function(*args, **kwargs)
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)        # disarm
    signal.signal(signal.SIGALRM, old_handler)     # restore
```

`setitimer` rather than `signal.alarm` because `alarm` only accepts whole
seconds; `setitimer` honors fractional `seconds`. The `finally` always disarms
the timer and restores any pre-existing handler, even when the wrapped function
raises a non-timeout exception.

### Sync — thread-pool fallback

```python
executor = ThreadPoolExecutor(max_workers=1)
future = executor.submit(function, *args, **kwargs)
try:
    return future.result(timeout=seconds)
except FuturesTimeoutError:
    raise TimeoutError(message) from None
finally:
    executor.shutdown(wait=False)
```

`concurrent.futures.TimeoutError` is imported as `FuturesTimeoutError` to avoid
shadowing the built-in. We do **not** use the `with` context manager because
its blocking join would wait on the orphan thread; `shutdown(wait=False)`
returns immediately.

### New imports

`signal`, `threading`, and from `concurrent.futures`: `ThreadPoolExecutor` and
`TimeoutError as FuturesTimeoutError`. `asyncio` is already imported.

## Timeout message

Consistent across all three paths:

```python
message = f"{function.__qualname__} timed out after {seconds} seconds"
```

## Edge cases

- `seconds <= 0` → `ValueError` at decoration time (avoids `setitimer(…, 0)`
  meaning "never fire" and `future.result(0)` racing).
- SIGALRM handler is always disarmed/restored via `finally`.
- Nested `@timeout` on the main thread: SIGALRM has a single timer, so nesting
  would clobber the outer timer. Documented as a limitation; no timer stack
  (YAGNI).

## Testing (`tests/test_utilities.py`)

Plain `pytest`, matching existing style (`if __name__ == "__main__"` runner).
Short sleeps (limit ~0.1s, sleep ~0.5s) keep the suite fast.

1. `test_timeout_sync_success` — fast sync function returns normally.
2. `test_timeout_sync_expires` — slow sync function raises `TimeoutError`
   (exercises SIGALRM path; pytest runs on the main thread).
3. `test_timeout_async_success` / `test_timeout_async_expires` — async
   equivalents via `asyncio.run` + `asyncio.sleep`.
4. `test_timeout_fallback_expires` — run the decorated call inside a non-main
   `threading.Thread` to force the thread-pool branch on any OS; assert
   `TimeoutError` is raised.
5. `test_timeout_invalid_seconds` — `@timeout(0)` raises `ValueError`.

## Docs

`docs/api/utilities.md` is auto-generated via `mkdocstrings`. A complete
docstring with an `Examples:` block (matching the other decorators) is
sufficient — no manual doc edits.

## Constraints

- Python 3.10+, strict mypy (`disallow_untyped_defs`), ruff line length 79,
  mccabe max-complexity 10. The branching may need small private helpers to
  stay under the complexity limit.
