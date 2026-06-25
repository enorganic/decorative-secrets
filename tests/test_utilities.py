from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import signal
import threading
from collections.abc import Iterator
from functools import partial
from time import sleep
from typing import TYPE_CHECKING

import pytest

from decorative_secrets.utilities import (
    _default_retry_hook,
    _run_with_sigalrm_timeout,
    as_dict,
    as_iter,
    as_str,
    as_tuple,
    create_async_log_warning_retry_hook,
    create_log_warning_retry_hook,
    get_exception_text,
    get_logger,
    iscoroutinefunction,
    retry,
    timeout,
    warn_retry_hook,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path


def test_as_dict() -> None:
    """
    Verify that the as_dict decorator works as intended.
    """

    @as_dict
    def get_key_value_pairs() -> Iterable[tuple[str, int]]:
        yield ("one", 1)
        yield ("two", 2)
        yield ("three", 3)

    assert get_key_value_pairs() == {"one": 1, "two": 2, "three": 3}


def test_as_iter() -> None:
    """
    Verify that the `as_iter` decorator works as intended.
    """

    @as_iter
    def get_key_value_pairs() -> Iterable[tuple[str, int]]:
        yield ("one", 1)
        yield ("two", 2)
        yield ("three", 3)

    assert isinstance(get_key_value_pairs(), Iterator)


def test_as_tuple() -> None:
    """
    Verify that the as_tuple decorator works as intended.
    """

    @as_tuple
    def get_numbers() -> Iterable[int]:
        yield 1
        yield 2
        yield 3

    assert get_numbers() == (1, 2, 3)


def test_as_str() -> None:
    """
    Verify that the as_str decorator works as intended.
    """

    @as_str(separator=", ")
    def get_fruits() -> Iterable[str]:
        yield "apple"
        yield "banana"
        yield "cherry"

    assert get_fruits() == "apple, banana, cherry"

    @as_str
    def get_vegetables() -> Iterable[str]:
        yield "carrot\n"
        yield "broccoli\n"
        yield "spinach"

    assert get_vegetables() == "carrot\nbroccoli\nspinach"


def test_timeout_sync_success() -> None:
    """
    A synchronous function which completes within the limit returns
    its value normally.
    """

    @timeout(1)
    def fast() -> str:
        return "ok"

    assert fast() == "ok"


def test_timeout_sync_expires() -> None:
    """
    A synchronous function which exceeds the limit raises `TimeoutError`.
    """

    @timeout(0.1)
    def slow() -> str:
        sleep(0.5)
        return "ok"

    with pytest.raises(TimeoutError):
        slow()


def test_timeout_async_success() -> None:
    """
    An asynchronous function which completes within the limit returns
    its value normally.
    """

    @timeout(1)
    async def fast() -> str:
        return "ok"

    assert asyncio.run(fast()) == "ok"


def test_timeout_async_expires() -> None:
    """
    An asynchronous function which exceeds the limit raises `TimeoutError`.
    """

    @timeout(0.1)
    async def slow() -> str:
        await asyncio.sleep(0.5)
        return "ok"

    with pytest.raises(TimeoutError):
        asyncio.run(slow())


def test_timeout_fallback_expires() -> None:
    """
    When the decorated function runs outside the main thread, the
    `SIGALRM` strategy is unavailable and the thread-pool fallback must
    still raise `TimeoutError`.
    """

    @timeout(0.1)
    def slow() -> str:
        sleep(0.5)
        return "ok"

    errors: list[BaseException] = []

    def run() -> None:
        try:
            slow()
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    assert len(errors) == 1
    assert isinstance(errors[0], TimeoutError)


def test_timeout_nested_outer_still_expires() -> None:
    """
    When a `@timeout`-decorated function calls another
    `@timeout`-decorated function on the main thread, the inner call must
    not disable the outer timeout: the outer timeout must still fire.
    """

    @timeout(0.2)
    def inner() -> str:
        return "inner"

    @timeout(0.3)
    def outer() -> str:
        inner()
        sleep(1.0)
        return "outer"

    with pytest.raises(TimeoutError):
        outer()


def test_timeout_fallback_uses_daemon_thread() -> None:
    """
    The thread fallback must run the function in a daemon thread so that a
    timed-out (or otherwise still-running) call cannot block interpreter
    shutdown by being joined at exit.
    """
    captured: list[bool] = []

    @timeout(1)
    def record() -> str:
        captured.append(threading.current_thread().daemon)
        return "ok"

    def run() -> None:
        # Running outside the main thread forces the thread fallback.
        record()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    assert captured == [True]


def _call_off_main_thread(call: Callable[[], object]) -> BaseException | None:
    """
    Invoke `call` on a non-main thread (forcing the `timeout` thread
    fallback) and return the exception it raised, or `None` if it returned
    normally.
    """
    outcome: list[BaseException] = []

    def target() -> None:
        try:
            call()
        except BaseException as error:  # noqa: BLE001
            outcome.append(error)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    return outcome[0] if outcome else None


def test_timeout_fallback_propagates_error() -> None:
    """
    When a function run via the thread fallback raises within the limit,
    the original exception propagates to the caller unchanged.
    """

    @timeout(1)
    def boom() -> str:
        message: str = "kaboom"
        raise ValueError(message)

    errors: list[BaseException] = []

    def run() -> None:
        try:
            boom()
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert str(errors[0]) == "kaboom"


def test_timeout_fallback_logs_late_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    In thread-pool fallback mode, when the abandoned worker thread raises
    after the timeout has already fired, the exception is logged rather
    than silently discarded.
    """

    @timeout(0.1)
    def slow() -> str:
        sleep(0.3)
        message: str = "late failure"
        raise RuntimeError(message)

    def run() -> None:
        # Running outside the main thread forces the thread-pool fallback.
        with contextlib.suppress(TimeoutError):
            slow()

    with caplog.at_level(logging.WARNING):
        thread = threading.Thread(target=run)
        thread.start()
        thread.join()
        # Wait for the abandoned worker to finish and log its failure.
        for _ in range(50):
            if any(
                "late failure" in record.getMessage()
                for record in caplog.records
            ):
                break
            sleep(0.05)

    assert any(
        "late failure" in record.getMessage() for record in caplog.records
    )


def test_timeout_fallback_boundary_never_drops_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    When a fallback function raises at almost exactly the timeout boundary,
    the exception must never be silently dropped: it is always either
    propagated to the caller or logged. This guards the race between the
    caller declaring a timeout and the worker reporting its outcome, which
    is exercised here by making the function raise at the moment the limit
    expires, repeated enough times to hit the racing interleaving.
    """
    limit: float = 0.01
    iterations: int = 80

    def make_boom(marker: str) -> Callable[[], None]:
        @timeout(limit)
        def boom() -> None:
            sleep(limit)
            raise ValueError(marker)

        return boom

    with caplog.at_level(logging.WARNING):
        for index in range(iterations):
            marker: str = f"boundary-{index}"
            error: BaseException | None = _call_off_main_thread(
                make_boom(marker)
            )
            if isinstance(error, ValueError):
                # The worker won the race; its error was propagated.
                continue
            # The caller saw a `TimeoutError`: the abandoned worker must
            # still log its late failure rather than discard it.
            for _ in range(20):
                if any(
                    marker in record.getMessage()
                    for record in list(caplog.records)
                ):
                    break
                sleep(0.01)
            else:
                pytest.fail(
                    f"error {marker!r} was neither propagated nor logged"
                )


def test_timeout_invalid_seconds() -> None:
    """
    A non-positive timeout raises `ValueError` at decoration time.
    """

    with pytest.raises(ValueError):  # noqa: PT011
        timeout(0)


@pytest.mark.skipif(
    not hasattr(signal, "SIGALRM"),
    reason="SIGALRM is unavailable on this platform",
)
def test_sigalrm_timeout_restores_preexisting_timer_and_handler() -> None:
    """
    The `SIGALRM` runner must restore any pre-existing `ITIMER_REAL` timer
    and signal handler on exit, rather than unconditionally cancelling them.
    This guards against a directly-reused runner silently swallowing an
    outer alarm.
    """

    def preexisting_handler(signal_number: int, frame: object) -> None:
        """A sentinel handler that should be restored, never invoked here."""

    original_handler = signal.signal(signal.SIGALRM, preexisting_handler)
    try:
        # Arm a long timer that must survive the inner, fast call without
        # firing during the test.
        signal.setitimer(signal.ITIMER_REAL, 60.0)
        result = _run_with_sigalrm_timeout(
            lambda: "ok", 0.5, "inner timed out", (), {}
        )
        assert result == "ok"
        remaining_delay, _ = signal.getitimer(signal.ITIMER_REAL)
        # The pre-existing timer is still pending (not cancelled)...
        assert remaining_delay > 0
        # ...and the original handler is restored.
        assert signal.getsignal(signal.SIGALRM) is preexisting_handler
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, original_handler)


def test_iscoroutinefunction() -> None:
    """
    Ensure that our `iscoroutinefunction` utility correctly identifies
    coroutine functions and synchronous functions.
    """

    def synchronous_function() -> None:
        return None

    assert iscoroutinefunction(synchronous_function) is False

    async def coroutine_function() -> None:
        return None

    assert iscoroutinefunction(coroutine_function) is True

    async def coroutine_value_function(value: int) -> int:
        return value

    assert iscoroutinefunction(partial(coroutine_value_function, 1)) is True
    assert iscoroutinefunction(partial(len)) is False


def test_as_tuple_async() -> None:
    """
    The `as_tuple` decorator wraps the awaited result of a coroutine
    function in a tuple.
    """

    @as_tuple
    async def get_numbers() -> Iterable[int]:
        return [1, 2, 3]

    assert asyncio.run(get_numbers()) == (1, 2, 3)


def test_as_str_async() -> None:
    """
    The `as_str` decorator joins the awaited result of a coroutine
    function into a single string.
    """

    @as_str(separator=", ")
    async def get_fruits() -> Iterable[str]:
        return ("apple", "banana", "cherry")

    assert (
        asyncio.run(get_fruits())  # type: ignore[arg-type]
        == "apple, banana, cherry"
    )


def test_as_dict_async() -> None:
    """
    The `as_dict` decorator builds a dictionary from the awaited result of
    a coroutine function.
    """

    @as_dict
    async def get_items() -> Iterable[tuple[str, int]]:
        return (("one", 1), ("two", 2))

    assert asyncio.run(get_items()) == {"one": 1, "two": 2}


def test_as_iter_async() -> None:
    """
    The `as_iter` decorator returns an iterator over the awaited result of
    a coroutine function.
    """

    @as_iter  # type: ignore[arg-type]
    async def get_numbers() -> Iterable[int]:
        return (1, 2, 3)

    result = asyncio.run(get_numbers())
    assert isinstance(result, Iterator)
    assert tuple(result) == (1, 2, 3)


STREAM_FIND_SLEEP_SECONDS = 0.01


def stream_until(stream: io.StringIO, value: str, timeout: float = 2.0) -> str:
    """
    Poll an in-memory log `stream` until `value` appears, then return the
    streamed output.

    Parameters:
        stream: An in-memory log stream.
        value: The value to search for in the stream.
        timeout: The maximum time to wait for the value to appear.
    """
    for _ in range(int(timeout / STREAM_FIND_SLEEP_SECONDS)):
        stream_value: str = stream.getvalue()
        if value in stream_value:
            return stream_value
        sleep(STREAM_FIND_SLEEP_SECONDS)
    return stream.getvalue()


def test_get_logger_creates_non_blocking_logger() -> None:
    """
    A freshly created logger has its level and propagation configured and
    a single (queue) handler attached.
    """
    logger: logging.Logger = get_logger(
        "test_get_logger_creates", level=logging.DEBUG, propagate=False
    )

    assert logger.level == logging.DEBUG
    assert logger.propagate is False
    assert len(logger.handlers) == 1


def test_get_logger_updates_existing_level() -> None:
    """
    Calling `get_logger` again for an existing logger updates the level on
    both the logger and its handlers without adding new handlers.
    """
    name: str = "test_get_logger_updates"
    first: logging.Logger = get_logger(name, level=logging.INFO)
    handler_count: int = len(first.handlers)
    second: logging.Logger = get_logger(name, level=logging.WARNING)
    assert second is first
    assert second.level == logging.WARNING
    assert len(second.handlers) == handler_count
    assert all(handler.level == logging.WARNING for handler in second.handlers)


def test_get_logger_with_stream_and_string_formatter() -> None:
    """
    When a stream and a format string are provided, emitted records are
    written to the stream formatted accordingly.
    """
    stream: io.StringIO = io.StringIO()
    logger: logging.Logger = get_logger(
        "test_get_logger_stream",
        level=logging.INFO,
        formatter="LEVEL=%(levelname)s MSG=%(message)s",
        stream=stream,
    )
    logger.info("hello")
    assert "LEVEL=INFO MSG=hello" in stream_until(stream, "hello")


def test_get_logger_with_formatter_instance() -> None:
    """
    A `logging.Formatter` instance is applied directly to the handler.
    """
    stream: io.StringIO = io.StringIO()
    logger: logging.Logger = get_logger(
        "test_get_logger_formatter_instance",
        level=logging.INFO,
        formatter=logging.Formatter("INSTANCE:%(message)s"),
        stream=stream,
    )
    logger.info("payload")
    assert "INSTANCE:payload" in stream_until(stream, "payload")


def test_get_logger_with_formatter_type() -> None:
    """
    A `logging.Formatter` subclass is instantiated and applied.
    """

    class PrefixFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            return f"TYPE:{record.getMessage()}"

    stream: io.StringIO = io.StringIO()
    logger: logging.Logger = get_logger(
        "test_get_logger_formatter_type",
        level=logging.INFO,
        formatter=PrefixFormatter,
        stream=stream,
    )
    logger.info("payload")
    assert "TYPE:payload" in stream_until(stream, "payload")


def test_get_logger_with_path(tmp_path: Path) -> None:
    """
    When given a path, the logger opens the file for writing and emits
    records to it.
    """
    log_path = tmp_path / "out.log"
    logger: logging.Logger = get_logger(
        "test_get_logger_path",
        level=logging.INFO,
        formatter="%(message)s",
        stream=str(log_path),
    )
    logger.info("to-file")
    for _ in range(200):
        if log_path.exists() and "to-file" in log_path.read_text():
            break
        sleep(0.01)
    assert "to-file" in log_path.read_text()


def test_default_retry_hook_returns_true() -> None:
    """
    The default retry hook allows any genuine error to be retried.
    """
    assert _default_retry_hook(ValueError("boom"), 1) is True


def test_default_retry_hook_falsy_error_raises() -> None:
    """
    The default retry hook rejects a falsy (missing) error.
    """
    with pytest.raises(ValueError):  # noqa: PT011
        _default_retry_hook(None, 1)  # type: ignore[arg-type]


def test_warn_retry_hook_warns() -> None:
    """
    `warn_retry_hook` issues a warning naming the attempt number and
    returns `True`.
    """
    with pytest.warns(UserWarning, match="Attempt # 3"):
        assert warn_retry_hook(ValueError("boom"), 3) is True


def test_create_log_warning_retry_hook_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    The hook built by `create_log_warning_retry_hook` logs a warning via
    the supplied logger and returns `True`.
    """
    logger: logging.Logger = logging.getLogger("test_retry_hook_logger")
    hook = create_log_warning_retry_hook(logger)
    with caplog.at_level(logging.WARNING, logger=logger.name):
        assert hook(ValueError("boom"), 2) is True
    assert any("boom" in record.getMessage() for record in caplog.records)


def test_create_log_warning_retry_hook_accepts_callable() -> None:
    """
    `create_log_warning_retry_hook` accepts a callable which returns a
    logger.
    """
    logger: logging.Logger = logging.getLogger("test_retry_hook_callable")
    hook = create_log_warning_retry_hook(lambda: logger)
    assert hook(ValueError("boom"), 1) is True


def test_create_log_warning_retry_hook_rejects_non_logger() -> None:
    """
    A value which is neither a logger nor a logger factory raises
    `TypeError`.
    """
    with pytest.raises(TypeError):
        create_log_warning_retry_hook(42)  # type: ignore[arg-type]


def test_create_async_log_warning_retry_hook_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    The async hook logs a warning via the supplied logger and returns
    `True`.
    """
    logger: logging.Logger = logging.getLogger("test_async_retry_hook_logger")
    hook = create_async_log_warning_retry_hook(logger)
    with caplog.at_level(logging.WARNING, logger=logger.name):
        assert asyncio.run(hook(ValueError("boom"), 5)) is True
    assert any("boom" in record.getMessage() for record in caplog.records)


def test_retry_sync_success() -> None:
    """
    A synchronous function which succeeds is called once and its value
    returned.
    """
    calls: list[int] = []

    @retry((ValueError,))
    def succeed() -> str:
        calls.append(1)
        return "ok"

    assert succeed() == "ok"
    assert len(calls) == 1


@pytest.mark.usefixtures("no_backoff")
def test_retry_sync_recovers() -> None:
    """
    A synchronous function which fails once then succeeds is retried and
    eventually returns its value.
    """
    calls: list[int] = []

    @retry((ValueError,), number_of_attempts=2)
    def flaky() -> str:
        calls.append(1)
        if len(calls) < 2:
            message: str = "boom"
            raise ValueError(message)
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 2


@pytest.mark.usefixtures("no_backoff")
def test_retry_sync_single_parameter_hook() -> None:
    """
    A retry hook accepting only the error (not the attempt number) is
    invoked with the error alone.
    """
    seen: list[BaseException] = []

    def hook(error: Exception) -> bool:
        seen.append(error)
        return True

    @retry((ValueError,), retry_hook=hook, number_of_attempts=2)
    def flaky() -> str:
        if not seen:
            message: str = "boom"
            raise ValueError(message)
        return "ok"

    assert flaky() == "ok"
    assert len(seen) == 1


@pytest.mark.usefixtures("no_backoff")
def test_retry_sync_hook_false_reraises() -> None:
    """
    When the retry hook returns `False`, the error is re-raised immediately
    without further attempts.
    """
    calls: list[int] = []

    def hook(error: Exception, attempt_number: int) -> bool:  # noqa: ARG001
        return False

    @retry((ValueError,), retry_hook=hook, number_of_attempts=3)
    def fail() -> None:
        calls.append(1)
        message: str = "boom"
        raise ValueError(message)

    with pytest.raises(ValueError):  # noqa: PT011
        fail()
    assert len(calls) == 1


@pytest.mark.usefixtures("no_backoff")
def test_retry_sync_exhausts() -> None:
    """
    When every attempt fails, the final error propagates to the caller.
    """
    calls: list[int] = []

    @retry((ValueError,), number_of_attempts=3)
    def always_fail() -> None:
        calls.append(1)
        message: str = "boom"
        raise ValueError(message)

    with pytest.raises(ValueError):  # noqa: PT011
        always_fail()
    assert len(calls) == 3


@pytest.mark.usefixtures("no_backoff")
def test_retry_sync_unhandled_error_propagates() -> None:
    """
    Ensure an error not listed in the retry `errors` parameter is propagated.
    """
    called: bool = False

    @retry((ValueError,), number_of_attempts=3)
    def fail() -> None:
        nonlocal called
        called = True
        message: str = "wrong type"
        raise KeyError(message)

    with pytest.raises(KeyError):
        fail()
    assert called


def test_retry_async_success() -> None:
    """
    An asynchronous function which succeeds is called once and its value
    returned.
    """

    @retry((ValueError,))
    async def succeed() -> str:
        return "ok"

    assert asyncio.run(succeed()) == "ok"


@pytest.mark.usefixtures("no_backoff")
def test_retry_async_recovers_with_sync_hook() -> None:
    """
    An async function retried with the default (synchronous) hook recovers
    after a transient failure.
    """
    calls: list[int] = []

    @retry((ValueError,), number_of_attempts=2)
    async def flaky() -> str:
        calls.append(1)
        if len(calls) < 2:
            message: str = "boom"
            raise ValueError(message)
        return "ok"

    assert asyncio.run(flaky()) == "ok"
    assert len(calls) == 2


@pytest.mark.usefixtures("no_backoff")
def test_retry_async_with_async_hook() -> None:
    """
    An async retry hook accepting the error and attempt number is awaited.
    """
    seen: list[int] = []

    async def hook(error: Exception, attempt_number: int) -> bool:  # noqa: ARG001
        seen.append(attempt_number)
        return True

    @retry((ValueError,), retry_hook=hook, number_of_attempts=2)
    async def flaky() -> str:
        if not seen:
            message: str = "Dummy Error"
            raise ValueError(message)
        return "ok"

    assert asyncio.run(flaky()) == "ok"
    assert seen == [1]


@pytest.mark.usefixtures("no_backoff")
def test_retry_async_with_single_parameter_async_hook() -> None:
    """
    An async retry hook accepting only the error is awaited with the error
    alone.
    """
    seen: list[BaseException] = []

    async def hook(error: Exception) -> bool:
        seen.append(error)
        return True

    @retry((ValueError,), retry_hook=hook, number_of_attempts=2)
    async def flaky() -> str:
        if not seen:
            message: str = "Dummy Error"
            raise ValueError(message)
        return "ok"

    assert asyncio.run(flaky()) == "ok"
    assert len(seen) == 1


@pytest.mark.usefixtures("no_backoff")
def test_retry_async_hook_false_reraises() -> None:
    """
    When an async retry's hook returns `False`, the error is re-raised
    immediately.
    """
    calls: list[int] = []

    def hook(error: Exception, attempt_number: int) -> bool:  # noqa: ARG001
        return False

    @retry((ValueError,), retry_hook=hook, number_of_attempts=3)
    async def fail() -> None:
        calls.append(1)
        message: str = "Dummy Error"
        raise ValueError(message)

    with pytest.raises(ValueError):  # noqa: PT011
        asyncio.run(fail())
    assert len(calls) == 1


@pytest.mark.usefixtures("no_backoff")
def test_retry_async_exhausts() -> None:
    """
    When every async attempt fails, the final error propagates.
    """
    call_count: int = 0

    @retry((ValueError,), number_of_attempts=2)
    async def always_fail() -> None:
        nonlocal call_count
        call_count += 1
        message: str = "Dummy Error"
        raise ValueError(message)

    with pytest.raises(ValueError):  # noqa: PT011
        asyncio.run(always_fail())
    assert call_count == 2


def test_get_exception_text_within_except() -> None:
    """
    `get_exception_text` returns the formatted traceback text of the
    currently handled exception.
    """
    try:
        message: str = "Dummy Error"
        raise ValueError(message)  # noqa: TRY301
    except ValueError:
        text: str = get_exception_text()

    assert "Traceback" in text
    assert "ValueError" in text
    assert "Dummy Error" in text


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
