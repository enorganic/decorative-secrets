import asyncio

import pytest

from decorative_secrets.defaults import (
    ApplyConditionalDefaultsOptions,
    apply_conditional_defaults,
)

DEV_RETURN_VALUE = ("dev", "/in/dev", "/out/dev")
STAGE_RETURN_VALUE = ("stage", "/in/stage", "/out/stage")
PROD_RETURN_VALUE = ("prod", "/in/prod", "/out/prod")


def test_apply_conditional_defaults() -> None:
    """
    Verify that the `apply_conditional_defaults` decorator works as intended.
    """

    @apply_conditional_defaults(
        lambda environment: environment == "prod",
        source_directory="/in/prod",
        target_directory="/out/prod",
    )
    @apply_conditional_defaults(
        lambda environment: environment == "dev",
        source_directory="/in/dev",
        target_directory="/out/dev",
    )
    @apply_conditional_defaults(
        lambda environment: environment == "stage",
        source_directory="/in/stage",
        target_directory="/out/stage",
    )
    def get_environment_source_target(
        environment: str = "dev",
        source_directory: str = "/dev/null",
        target_directory: str = "/dev/null",
    ) -> tuple[str, str, str]:
        return (environment, source_directory, target_directory)

    # The default environment is "dev", so without any arguments, we should get
    # the "dev" source and target directories
    assert get_environment_source_target() == DEV_RETURN_VALUE
    # ...same when explicitly passing "dev" as a keyword argument
    assert get_environment_source_target(environment="dev") == DEV_RETURN_VALUE
    # ...same when explicitly passing "dev" as a positional argument
    assert get_environment_source_target("dev") == DEV_RETURN_VALUE
    # ...prod
    assert (
        get_environment_source_target(environment="prod") == PROD_RETURN_VALUE
    )
    assert get_environment_source_target("prod") == PROD_RETURN_VALUE
    # ...stage
    assert (
        get_environment_source_target(environment="stage")
        == STAGE_RETURN_VALUE
    )
    assert get_environment_source_target("stage") == STAGE_RETURN_VALUE


def test_apply_conditional_defaults_filter_parameter_defaults() -> None:
    """
    Verify that the `apply_conditional_defaults` decorator works as intended
    when paired with the `ApplyConditionalDefaultsOptions` class to filter
    out explicit `None` keyword arguments.
    """

    @apply_conditional_defaults(
        lambda environment: environment == "prod",
        ApplyConditionalDefaultsOptions(filter_parameter_defaults=(None,)),
        source_directory="/in/prod",
        target_directory="/out/prod",
    )
    @apply_conditional_defaults(
        lambda environment: environment == "dev",
        ApplyConditionalDefaultsOptions(filter_parameter_defaults=(None,)),
        source_directory="/in/dev",
        target_directory="/out/dev",
    )
    @apply_conditional_defaults(
        lambda environment: environment == "stage",
        ApplyConditionalDefaultsOptions(filter_parameter_defaults=(None,)),
        source_directory="/in/stage",
        target_directory="/out/stage",
    )
    def get_environment_source_target(
        environment: str = "dev",
        source_directory: str | None = None,
        target_directory: str | None = None,
    ) -> tuple[str, str | None, str | None]:
        return (environment, source_directory, target_directory)

    # The default environment is "dev", so without any arguments, we should get
    # the "dev" source and target directories
    assert (
        get_environment_source_target(
            source_directory=None, target_directory=None
        )
        == DEV_RETURN_VALUE
    )
    # ...same when explicitly passing "dev" as a keyword argument
    assert (
        get_environment_source_target(
            environment="dev", source_directory=None, target_directory=None
        )
        == DEV_RETURN_VALUE
    )
    # ...same when explicitly passing "dev" as a positional argument
    assert (
        get_environment_source_target("dev", None, target_directory=None)
        == DEV_RETURN_VALUE
    )
    # ...prod
    assert (
        get_environment_source_target(
            environment="prod", source_directory=None, target_directory=None
        )
        == PROD_RETURN_VALUE
    )
    assert (
        get_environment_source_target("prod", None, None) == PROD_RETURN_VALUE
    )
    # ...stage
    assert (
        get_environment_source_target(
            environment="stage", source_directory=None, target_directory=None
        )
        == STAGE_RETURN_VALUE
    )
    assert (
        get_environment_source_target("stage", None, None)
        == STAGE_RETURN_VALUE
    )


def test_apply_conditional_defaults_extends_positional_args() -> None:
    """
    When defaults are supplied positionally and the call provides fewer
    positional arguments than there are defaults, the trailing defaults
    extend the positional arguments. The default aligned with an
    already-supplied position is skipped.
    """

    @apply_conditional_defaults(
        lambda flag: flag, None, "default_a", "default_b"
    )
    def function(
        flag: bool,  # noqa: FBT001
        /,
        a: str | None = None,
        b: str | None = None,
    ) -> tuple[bool, str | None, str | None]:
        return (flag, a, b)

    # `flag` occupies position 0 (so the first default, `None`, is skipped);
    # the remaining defaults fill `a` and `b`.
    assert function(True) == (True, "default_a", "default_b")


def test_apply_conditional_defaults_async() -> None:
    """
    The decorator wraps coroutine functions, applying defaults before
    awaiting the wrapped function.
    """

    @apply_conditional_defaults(
        lambda environment: environment == "dev",
        source_directory="/in/dev",
    )
    async def get_source(
        environment: str = "dev",
        source_directory: str = "/dev/null",
    ) -> tuple[str, str]:
        await asyncio.sleep(0)
        return (environment, source_directory)

    assert asyncio.run(get_source()) == ("dev", "/in/dev")


if __name__ == "__main__":
    pytest.main(["-s", "-vv", __file__])
