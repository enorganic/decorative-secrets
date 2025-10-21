from __future__ import annotations

import argparse
import os
import sys
from contextlib import suppress
from functools import cache, partial
from shutil import which
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, Any
from urllib.request import urlopen

from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config

from decorative_secrets._utilities import (
    which_brew,
    which_winget,
)
from decorative_secrets.callback import apply_callback_arguments
from decorative_secrets.errors import (
    DatabricksCLINotInstalledError,
    HomebrewNotInstalledError,
)
from decorative_secrets.subprocess import check_call, check_output

if TYPE_CHECKING:
    from collections.abc import Callable

    from databricks.sdk.dbutils import RemoteDbUtils


def apply_databricks_secrets_arguments(
    *args: Config,
    **kwargs: str,
) -> Callable:
    """
    This decorator maps parameter names to Databricks secrets.
    Each key in `databricks_secret_arguments` represents the name of a
    parameter in the decorated function which accepts an explicit input, and
    the corresponding mapped value is a parameter name accepting a tuple with
    the secret scope and key with which to lookup a secret to pass to the
    mapped parameter in lieu of an explicitly provided argument.

    Parameters:
        *args: A `databricks.sdk.Config` instance to configure
            a workspace client when retrieving secrets remotely
            (if more than one  is provided, only the first is used).
        **kwargs: A mapping of static parameter names to the parameter names
            of arguments accepting Databricks secret scope + key tuples
            from which to retrieve a value when the key argument is not
            explicitly provided.

    Example:
        ```python
        from functools import (
            cache,
        )
        from decorative_secrets.databricks import (
            apply_databricks_secret_arguments,
        )
        from my_client_sdk import (
            Client,
        )


        @cache
        @apply_databricks_secret_arguments(
            client_id="client_id_databricks_secret",
            client_secret="client_secret_databricks_secret",
        )
        def get_client(
            client_id: str | None = None,
            client_secret: str = None,
            client_id_databricks_secret: str | None = None,
            client_secret_databricks_secret: str | None = None,
        ) -> Client:
            return Client(
                oauth2_client_id=client_id,
                oauth2_client_secret=client_secret,
            )


        client: Client = get_client(
            client_id_databricks_secret=(
                "client",
                "client-id",
            ),
            client_secret_databricks_secret=(
                "client",
                "client-secret",
            ),
        )
        ```
    """
    config: Config | None = _get_args_config(*args)[1]
    get_scope_key_secret: Callable[[str | tuple[str, str]], str] = partial(
        _get_scope_key_secret,
        config=config,
    )
    return apply_callback_arguments(
        get_scope_key_secret,
        **kwargs,
    )


def _install_sh_databricks_cli() -> None:
    """
    Install the Databricks CLI using the install script.
    """
    with urlopen(
        "https://raw.githubusercontent.com/databricks/setup-cli/"
        "main/install.sh"
    ) as install_io:
        sh: str = which("sh") or "sh"
        try:
            check_call((sh,), input=install_io.read())
        except (CalledProcessError, FileNotFoundError) as error:
            if (
                (not isinstance(error, CalledProcessError))
                or (not error.stdout)
                or (
                    (b"already exists" not in error.stdout)
                    and (b"'sudo'" not in error.stdout)
                )
            ):
                # This is usually because the script requires `sudo` access to
                # run
                raise DatabricksCLINotInstalledError from error


def _install_databricks_cli() -> None:
    """
    Install the Databricks CLI.
    """
    if sys.platform.startswith("win"):
        winget: str | None = which_winget()
        if winget:
            with suppress(CalledProcessError):
                check_output((winget, "search", "DatabricksCLI"))
            with suppress(CalledProcessError):
                check_output((winget, "install", "Databricks.DatabricksCLI"))
                return
    elif sys.platform == "darwin":
        brew: str
        # Here we suppress the HomebrewNotInstalledError because we
        # can still attempt to install the Databricks CLI using
        # the install script
        with suppress(HomebrewNotInstalledError):
            brew = which_brew()
            if brew:
                with suppress(CalledProcessError):
                    check_output((brew, "tap", "databricks/tap"))
                with suppress(CalledProcessError):
                    check_output((brew, "install", "databricks"))
                    return
    _install_sh_databricks_cli()


def which_databricks() -> str:
    """
    Find the `databricks` executable, or install the Databricks CLI if not
    found.
    """
    databricks: str = which("databricks") or "databricks"
    try:
        check_output((databricks, "--version"))
    except (CalledProcessError, FileNotFoundError):
        _install_databricks_cli()
        databricks = which("databricks") or "databricks"
    return databricks


@cache
def _databricks_auth_login(host: str | None = None) -> None:
    if host is None:
        host = os.getenv("DATABRICKS_HOST")
    databricks = which_databricks()
    if host:
        check_call((databricks, "auth", "login", "--host", host), input=b"\n")
    else:
        # Automatically select the default/first profile if no host
        # is specified
        check_call((databricks, "auth", "login"), input=b"\n\n")


def databricks_auth_login(host: str | None = None) -> None:
    """
    Log in to Databricks using the CLI if not already logged in.
    """
    return _databricks_auth_login(host or os.getenv("DATABRICKS_HOST"))


@cache
def _get_env_databricks_workspace_client(
    config: Config | None = None,
    **env: str,  # noqa: ARG001
) -> WorkspaceClient:
    """
    Get a Databricks WorkspaceClient. This function is cached based on
    environment variables, to ensure changes to the environment are reflected.
    """
    if not (
        config
        and (config.client_id or os.getenv("DATABRICKS_CLIENT_ID"))
        and (config.client_secret or os.getenv("DATABRICKS_CLIENT_SECRET"))
    ):
        with suppress(
            CalledProcessError,
            FileNotFoundError,
            DatabricksCLINotInstalledError,
        ):
            databricks_auth_login()
    return WorkspaceClient(
        config=config,
    )


def _get_databricks_workspace_client(
    config: Config | None = None,
) -> WorkspaceClient:
    """
    Get a Databricks WorkspaceClient configured from environment variables.
    """
    return _get_env_databricks_workspace_client(
        config=config,
        **os.environ,
    )


def get_dbutils(
    config: Config | None = None,
) -> RemoteDbUtils:  # pragma: no cover - environment dependent
    """
    Get [dbutils](https://docs.databricks.com/dev-tools/databricks-utils.html)
    using an existing instance from the runtime if found, otherwise,
    creating one using a workspace client (this requires either having
    [these environment variables set
    ](https://docs.databricks.com/aws/en/dev-tools/auth#environment-variables),
    or providing the equivalent optional arguments.
    """
    dbutils: RemoteDbUtils | None = None
    with suppress(ImportError):
        from IPython.core.getipython import (  # type: ignore[import-not-found]
            get_ipython,
        )

        if TYPE_CHECKING:
            from IPython.core.interactiveshell import (  # type: ignore[import-not-found]
                InteractiveShell,
            )

        ipython: InteractiveShell = get_ipython()
        if ipython is not None:
            user_namespace_attribute: str
            user_namespace: dict
            for user_namespace_attribute in "user_ns", "user_global_ns":
                dbutils = getattr(ipython, user_namespace_attribute, {}).get(
                    "dbutils", None
                )
                if dbutils is not None:
                    return dbutils
    dbutils = globals().get("dbutils")
    if dbutils is not None:
        return dbutils
    databricks_workspace_client: WorkspaceClient = (
        _get_databricks_workspace_client(
            config=config,
        )
    )
    return databricks_workspace_client.dbutils


@cache
def _get_secret(
    scope: str,
    key: str,
    config: Config | None = None,
    **env: str,  # noqa: ARG001
) -> str:
    """
    Get a secret from Databricks, and cache it based on parameters and
    environment variables (since these can change the host and authentication).
    """
    dbutils = get_dbutils(
        config=config,
    )
    return dbutils.secrets.get(scope, key)


def get_databricks_secret(
    scope: str,
    key: str,
    config: Config | None = None,
) -> str:
    """
    Get a secret from Databricks.
    """
    return _get_secret(
        scope,
        key,
        config=config,
        **os.environ,
    )


def _get_scope_key_secret(
    scope_key: tuple[str, str] | str,
    config: Config | None = None,
) -> str:
    if isinstance(scope_key, str):
        scope_key = scope_key.partition("/")[::2]
    return get_databricks_secret(
        *scope_key,
        config=config,
    )


def _get_args_config(*args: Any) -> tuple[tuple[Any, ...], Config | None]:
    """
    This function extracts an instance of `databricks.sdk.Config`
    from the provided arguments, if one is present.
    """
    index: int
    value: Any
    for index, value in enumerate(args):
        if isinstance(value, Config):
            return (*args[:index], *args[index + 1 :]), value
    return args, None


def _print_help() -> None:
    print(  # noqa: T201
        "Usage:\n"
        "  decorative-secrets databricks <command> [options]\n\n"
        "Commands:\n"
        "  install\n"
        "  get"
    )


def _get_command() -> str:
    command: str = ""
    if len(sys.argv) > 1:
        command = sys.argv.pop(1).lower().replace("_", "-")
    return command


def main() -> None:
    """
    Run a command:
    -   install: Install the Databricks CLI if not already installed
    -   get: Get a secret from Databricks and print it to stdout
    """
    command = _get_command()
    if command in ("--help", "-h"):
        _print_help()
        return
    parser: argparse.ArgumentParser
    if command == "install":
        parser = argparse.ArgumentParser(
            prog="decorative-secrets databricks install",
            description="Install the Databricks CLI",
        )
        parser.parse_args()
        _install_databricks_cli()
    elif command == "get":
        parser = argparse.ArgumentParser(
            prog="decorative-secrets databricks get",
            description="Get a secret from Databricks",
        )
        parser.add_argument(
            "scope",
            type=str,
        )
        parser.add_argument(
            "key",
            type=str,
        )
        parser.add_argument(
            "--host",
            default=None,
            type=str,
            help="A Databricks workspace host URL",
        )
        parser.add_argument(
            "-cid",
            "--client-id",
            default=None,
            type=str,
            help="A Databricks OAuth2 Client ID",
        )
        parser.add_argument(
            "-cs",
            "--client-secret",
            default=None,
            type=str,
            help="A Databricks OAuth2 Client Secret",
        )
        parser.add_argument(
            "-t",
            "--token",
            default=None,
            type=str,
            help="A Databricks Personal Access Token",
        )
        parser.add_argument(
            "-p",
            "--profile",
            default=None,
            type=str,
            help="A Databricks Configuration Profile",
        )
        namespace: argparse.Namespace = parser.parse_args()
        config: Config | None = None
        if (
            namespace.host
            or namespace.client_id
            or namespace.client_secret
            or namespace.token
            or namespace.profile
        ):
            config = Config(
                host=namespace.host,
                client_id=namespace.client_id,
                client_secret=namespace.client_secret,
                token=namespace.token,
                profile=namespace.profile,
            )
        print(  # noqa: T201
            get_databricks_secret(
                namespace.scope,
                namespace.key,
                config=config,
            )
        )


if __name__ == "__main__":
    main()
