from __future__ import annotations

import argparse
import asyncio
import os
import sys
from contextlib import suppress
from dataclasses import dataclass
from functools import cache, partial
from importlib.metadata import distribution
from shutil import which
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, Any
from urllib.parse import ParseResult, urlparse

from async_lru import alru_cache
from onepassword.client import Client  # type: ignore[import-untyped]
from onepasswordconnectsdk.client import (  # type: ignore[import-untyped]
    AsyncClient,
    Item,
)
from onepasswordconnectsdk.client import (  # type: ignore[import-untyped]
    Client as ConnectClient,
)

from decorative_secrets._utilities import (  # type: ignore[import-untyped]
    which_brew,
    which_winget,
)
from decorative_secrets.callback import apply_callback_arguments
from decorative_secrets.errors import (
    OnePasswordCommandLineInterfaceNotInstalledError,
    WinGetNotInstalledError,
)
from decorative_secrets.subprocess import check_output

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable

    from onepassword import Secrets  # type: ignore[import-untyped]
    from onepasswordconnectsdk.models.field import (  # type: ignore[import-untyped]
        Field,
    )

_INTEGRATION_NAME: str = "decorative-secrets"
_INTEGRATION_VERSION: str = distribution("decorative-secrets").version


def apply_onepassword_arguments(
    *args: ApplyOnepasswordArgumentsOptions,
    **kwargs: str,
) -> Callable:
    """
    This decorator maps parameter names to 1Password resources.
    Each key represents the name of a parameter in the decorated function
    which accepts an explicit input, and the corresponding mapped value is a
    parameter name accepting a resource path with which to lookup a secret
    to pass to the mapped parameter in lieu of an explicitly provided
    argument.

    Parameters:
        *args: An optional [ApplyOnepasswordArgumentsOptions
            ](./#decorative_secrets.onepassword.ApplyOnepasswordArgumentsOptions)
            instance governing the behavior of this decorator. If not provided,
            a default instance of [ApplyOnepasswordArgumentsOptions()
            ](./#decorative_secrets.onepassword.ApplyOnepasswordArgumentsOptions)
            will be used. If multiple instances are provided, only the first
            will be used.
        **kwargs:
            A mapping of static parameter names to the parameter names
            of arguments accepting 1Password resource paths from which to
            retrieve the value when the key argument is not explicitly
            provided.

    Example:
        ```python
        from functools import (
            cache,
        )
        from decorative_secrets.onepassword import (
            apply_onepassword_arguments,
        )
        from my_client_sdk import (
            Client,
        )


        @cache
        @apply_onepassword_arguments(
            client_id="client_id_onepassword",
            client_secret="client_secret_onepassword",
        )
        def get_client(
            client_id: str | None = None,
            client_secret: str = None,
            client_id_onepassword: str | None = None,
            client_secret_onepassword: str | None = None,
        ) -> Client:
            return Client(
                oauth2_client_id=client_id,
                oauth2_client_secret=client_secret,
            )


        client: Client = get_client(
            client_id_onepassword=(
                "op://Vault Name/Client ID Item Name/username",
            ),
            client_secret_onepassword=(
                "op://Vault Name/Client Secret Item Name/credential",
            ),
        )
        ```
    """
    options: ApplyOnepasswordArgumentsOptions
    args, options = _get_args_options(*args)
    read_onepassword_secret_: Callable[..., str] = read_onepassword_secret
    async_read_onepassword_secret_: Callable[
        [str, str | None, str | None, str | None], Coroutine[Any, Any, str]
    ] = async_read_onepassword_secret
    if (
        (options.account is not None)
        or (options.token is not None)
        or (options.host is not None)
    ):
        read_onepassword_secret_ = partial(
            read_onepassword_secret_,
            **({"account": options.account} if options.account else {}),
            **({"token": options.token} if options.token else {}),
            **({"host": options.host} if options.host else {}),
        )
        async_read_onepassword_secret_ = partial(
            async_read_onepassword_secret_,
            **({"account": options.account} if options.account else {}),
            **({"token": options.token} if options.token else {}),
            **({"host": options.host} if options.host else {}),
        )
    return apply_callback_arguments(
        read_onepassword_secret_,
        async_read_onepassword_secret_,
        **kwargs,
    )


def _install_op() -> None:
    """
    Install the 1Password CLI.
    """
    message: str
    if sys.platform.startswith("win"):
        try:
            check_output((which_winget(), "install", "1password-cli"))
        except (
            CalledProcessError,
            FileNotFoundError,
            WinGetNotInstalledError,
        ) as error:
            raise OnePasswordCommandLineInterfaceNotInstalledError from error
    elif sys.platform == "darwin":
        try:
            check_output((which_brew(), "install", "1password-cli"))
        except (CalledProcessError, FileNotFoundError) as error:
            raise OnePasswordCommandLineInterfaceNotInstalledError from error
    else:
        raise OnePasswordCommandLineInterfaceNotInstalledError


def which_op() -> str:
    """
    Locate the 1Password CLI executable, or attempt
    to install it if not found.
    """
    op: str = which("op") or "op"
    try:
        check_output((op, "--version"))
    except (CalledProcessError, FileNotFoundError):
        _install_op()
        op = which("op") or "op"
    return op


@cache
def _op_signin(account: str | None = None) -> str:
    op: str = which_op()
    if not account:
        account = os.getenv("OP_ACCOUNT")
    check_output(
        (op, "signin", "--account", account) if account else (op, "signin"),
        input=None if account else b"\n\n",
    )
    return op


def iter_op_account_list() -> Iterable[str]:
    """
    Yield all 1password account names.
    """
    op: str = which_op()
    line: str
    for line in check_output((op, "account", "list")).strip().split("\n")[1:]:
        yield line.partition(" ")[0]


def op_signin(account: str | None = None) -> str:
    """
    Sign in to 1Password using the CLI if not already signed in.
    """
    account = account or os.getenv("OP_ACCOUNT")
    if account:
        return _op_signin(account)
    op: str | None = None
    for account in iter_op_account_list():
        op = _op_signin(account)
    return op or which_op()


def _resolve_auth_arguments(
    account: str | None = None,
    token: str | None = None,
    host: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """
    Parameters:
        account:
        token:
        host:
    """
    if account is None:
        account = os.getenv("OP_ACCOUNT")
    if token is None:
        token = os.getenv("OP_SERVICE_ACCOUNT_TOKEN")
    if host is None:
        host = os.getenv("OP_CONNECT_HOST")
    if (token is None) or (host is not None):
        token = os.getenv("OP_CONNECT_TOKEN") or token
    return account, token, host


def _parse_resource(resource: str) -> tuple[str, str, str]:
    parse_result: ParseResult = urlparse(resource)
    return (parse_result.netloc, *parse_result.path[1:].partition("/")[::2])


async def _async_resolve_resource(token: str, resource: str) -> str:
    """
    Asynchronously resolve a 1Password resource using the
    `onepassword-sdk` library.
    """
    client: Client = await Client.authenticate(
        auth=token,
        integration_name=_INTEGRATION_NAME,
        integration_version=_INTEGRATION_VERSION,
    )
    secrets: Secrets = client.secrets
    return await secrets.resolve(resource)


async def _async_resolve_connect_resource(
    token: str, host: str, resource: str
) -> str:  # pragma: no cover
    connect_client: AsyncClient = AsyncClient(
        url=host,
        token=token,
    )
    vault: str
    item_name: str
    field_id: str
    vault, item_name, field_id = _parse_resource(resource)
    item: Item = await connect_client.get_item(item=item_name, vault=vault)
    field: Field
    for field in item.fields:
        if field.id == field_id:
            return field.value
    raise KeyError(resource)


def _resolve_connect_resource(
    token: str, host: str, resource: str
) -> str:  # pragma: no cover
    connect_client: ConnectClient = ConnectClient(
        url=host,
        token=token,
    )
    vault: str
    item_name: str
    field_id: str
    vault, item_name, field_id = _parse_resource(resource)
    item: Item = connect_client.get_item(item=item_name, vault=vault)
    field: Field
    for field in item.fields:
        if field.id == field_id:
            return field.value
    raise KeyError(resource)


@alru_cache(maxsize=None)
async def async_read_onepassword_secret(
    resource: str,
    account: str | None = None,
    token: str | None = None,
    host: str | None = None,
) -> str:
    """
    Asynchronously read a secret from 1Password using either the
    `onepassword-sdk` or `onepasswordconnectsdk` libraries, or the `op`
    executable (1password CLI), depending on the provided arguments and
    environment variables.

    Parameters:
        resource: A 1Password secret resource path. For example:
            "op://Vault Name/Client Secret Item Name/credential"
        account: A 1Password account URL. For example, individuals and families
            will use "my.1password.com", while teams and businesses will use
            a custom subdomain. This is only necessary when using
            the 1Password CLI where multiple accounts are configured.
        token: A 1Password or 1Password connect service account token.
        host: A 1Password Connect host URL. This is required when using
            self-hosted 1Password Connect.

    Returns:
        The resolved secret value.
    """
    account, token, host = _resolve_auth_arguments(account, token, host)
    if token:
        if host:
            return await _async_resolve_connect_resource(token, host, resource)
        return await _async_resolve_resource(token, resource)
    op: str | None = None
    with suppress(FileNotFoundError, CalledProcessError):
        op = op_signin(account)
    if not op:
        op = which_op() or "op"
    return check_output(
        (op, "read")
        + (("--account", account) if account else ())
        + (("--session", token) if token else ())
        + (resource,)
    )


@cache
def _read_onepassword_secret(
    resource: str,
    account: str | None = None,
    token: str | None = None,
    host: str | None = None,
    **env: str,  # noqa: ARG001
) -> str:
    """
    This function is wrapped by `read_onepassword_secret` to allow caching
    to be invalidated based on environment variable changes.
    """
    account, token, host = _resolve_auth_arguments(account, token, host)
    if token:
        if host:
            return _resolve_connect_resource(token, host, resource)
        return asyncio.run(_async_resolve_resource(token, resource))
    op: str | None = None
    with suppress(FileNotFoundError, CalledProcessError):
        op = op_signin(account)
    if not op:
        op = which_op() or "op"
    return check_output(
        (op, "read")
        + (("--account", account) if account else ())
        + (("--session", token) if token else ())
        + (resource,)
    )


def get_onepassword_secret(
    resource: str,
    account: str | None = None,
    token: str | None = None,
    host: str | None = None,
) -> str:
    """
    Read a secret from 1Password using either the `onepassword-sdk` or
    `onepasswordconnectsdk` libraries, or the `op` executable (1password CLI),
    depending on the provided arguments and environment variables.

    Parameters:
        resource: A 1Password secret resource path. For example:
            "op://Vault Name/Client Secret Item Name/credential"
        account: A 1Password account URL. For example, individuals and families
            will use "my.1password.com", while teams and businesses will use
            a custom subdomain. This is only necessary when using
            the 1Password CLI where multiple accounts are configured.
        token: A 1Password or 1Password connect service account token.
        host: A 1Password Connect host URL. This is required when using
            self-hosted 1Password Connect.

    Returns:
        The resolved secret value.
    """
    return _read_onepassword_secret(
        resource, account=account, token=token, host=host, **os.environ
    )


# For backward compatibility
read_onepassword_secret = get_onepassword_secret  # type: ignore[assignment]


@dataclass(frozen=True)
class ApplyOnepasswordArgumentsOptions:
    """
    This class contains options governing the behavior of the
    [apply_onepassword_arguments
    ](./#decorative_secrets.onepassword.apply_onepassword_arguments) decorator.

    Attributes:
        account: A 1Password account URL. For example, individuals
            and families will use "my.1password.com", while teams and
            businesses will use a custom subdomain. If not provided, the
            `OP_ACCOUNT` environment variable will be used, if set. This is
            only necessary when using the 1Password CLI where multiple
            accounts are configured, and if no token is provided or inferred
            from an environment variable.
        token: A 1Password or 1Password connect service account
            token. If not provided, the `OP_SERVICE_ACCOUNT_TOKEN` or
            `OP_CONNECT_TOKEN` environment variables will be used, if set.
        host: A 1Password Connect host URL. If not
            provided, the `OP_CONNECT_HOST` environment variable will be used,
            if set. This is required when using a self-hosted 1Password
            Connect server.
    """

    account: str | None = None
    token: str | None = None
    host: str | None = None


def _get_args_options(
    *args: Any,
) -> tuple[tuple[Any, ...], ApplyOnepasswordArgumentsOptions]:
    """
    This function extracts an `ApplyEnvironmentArgumentsOptions` instance
    from the provided arguments, if one is present.
    """
    index: int
    value: Any
    for index, value in enumerate(args):
        if isinstance(value, ApplyOnepasswordArgumentsOptions):
            return (*args[:index], *args[index + 1 :]), value
    return args, ApplyOnepasswordArgumentsOptions()


def _print_help() -> None:
    print(  # noqa: T201
        "Usage:\n"
        "  decorative-secrets onepassword <command> [options]\n\n"
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
            prog="decorative-secrets onepassword install",
            description="Install the 1Password CLI",
        )
        parser.parse_args()
        _install_op()
    elif command == "get":
        parser = argparse.ArgumentParser(
            prog="decorative-secrets onepassword get",
            description="Get a secret from 1Password",
        )
        parser.add_argument(
            "reference",
            type=str,
        )
        parser.add_argument(
            "--account",
            default=None,
            type=str,
            help="Which 1Password account to use",
        )
        parser.add_argument(
            "-t",
            "--token",
            default=None,
            type=str,
            help="A 1Password Service Account Token",
        )
        parser.add_argument(
            "--host",
            default=None,
            type=str,
            help="A 1Password Connect Host URL",
        )
        namespace: argparse.Namespace = parser.parse_args()
        print(  # noqa: T201
            read_onepassword_secret(
                namespace.reference,
                host=namespace.host,
                account=namespace.account,
                token=namespace.token,
            )
        )


if __name__ == "__main__":
    main()
