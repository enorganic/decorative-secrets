from subprocess import check_call

from decorative_secrets.defaults import apply_conditional_defaults

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


if __name__ == "__main__":
    check_call(("pytest", "-s", "-vv", __file__))
