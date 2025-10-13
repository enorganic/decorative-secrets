# decorative-secrets

[![test](https://github.com/enorganic/decorative-secrets/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/enorganic/decorative-secrets/actions/workflows/test.yml)
[![PyPI version](https://badge.fury.io/py/decorative-secrets.svg?icon=si%3Apython)](https://badge.fury.io/py/decorative-secrets)

This library implements decorators for mapping parameters passing
sensitive data, such as authentication credentials, to alternate parameters
indicating where the same credentials can be retrieved dynamically from a
secrets manager and/or environment variables. The use of a decorator pattern
to expose multiple authentication mechanisms is intended to facilitate
development practices which maintain a semblance of harmony between security
hygiene and test-driven development.

- [Documentation](https://decorative-secrets.enorganic.org)
- [Contributing](https://decorative-secrets.enorganic.org/contributing)

Currently, the following secret sources are supported:

-   [Databricks Secrets](https://docs.databricks.com/aws/en/security/secrets/)
    (`pip3 install decorative-secrets[databricks]`)
-   [1Password](https://1password.com/)
    (`pip3 install decorative-secrets[onepassword]`):
    1Password secrets are retrieved dynamically using the [1Password CLI
    ](https://developer.1password.com/docs/cli/)
    under the hood. This mechanism can be used with the 1Password desktop
    client and CLI (including via SSO), in which case a popup window will
    prompt for authentication during execution, or can use a [1Password
    service account](https://developer.1password.com/docs/service-accounts/)
    by setting the `OP_SERVICE_ACCOUNT_TOKEN` environment variable. The former
    is recommended for local development and testing, the latter for CI/CD
    and/or hosted applications.
-   Environment Variables

Future development will target support for AWS Secrets Manager,
Google Cloud Secret Manager, and Azure Key Vault.

## Installation

You can install `decorative-secrets` with pip:

```shell
pip3 install decorative-secrets
```

## Example Usage

```python
from functools import cache
from my_app_sdk.client import Client
from decorative_secrets.environment import apply_environment_arguments
from decorative_secrets.onepassword import apply_onepassword_arguments
from decorative_secrets.databricks import apply_databricks_secrets_arguments

@cache
@apply_environment_arguments(
  client_id="client_id_environment_variable",
  client_secret="client_secret_environment_variable",
)
@apply_databricks_secrets_arguments(
  client_id="client_id_databricks_secret",
  client_secret="client_secret_databricks_secret",
)
@apply_onepassword_arguments(
  client_id="client_id_onepassword",
  client_secret="client_secret_onepassword",
)
def get_client(
    client_id: str | None = None,
    client_secret: str = None,
    client_id_databricks_secret: tuple[str, str] | None = None,
    client_secret_databricks_secret: tuple[str, str] | None = None,
    client_id_onepassword: str | None = None,
    client_secret_onepassword: str | None = None,
    client_id_environment_variable: str | None = None,
    client_secret_environment_variable: str | None = None,
) -> Client:
    """
    This function is an example use of `decorative-secrets`.
    The returned client will authenticate with explicitly provided
    credentials if a `client_id` and `client_secret` are passed as arguments,
    otherwise, the same function call will first check to see if
    environment variables can be used, then will check to see if databricks
    secrets can be used, and lastly will check to see if 1password
    stored credentials can be obtained. In all cases where
    an argument other than `None` is passed, errors will be caught and
    accumulated for that parameter, but only raised if none of the
    successive mechanisms for retrieving a value for the parameter are
    successful.
    
    Parameters:
        client_id: An eplicitly passed OAuth 2 client ID
        client_secret: An explicitly passed OAuth 2 client secret
        client_id_databricks_secret: A databricks secrets scope and key
        from which to retrieve the client ID, if executed in a Databricks
        Runtime environment
        client_secret_databricks_secret: A databricks secrets scope and key
        from which to retrieve the client secret, if executed in a Databricks
        Runtime environment
        client_id_onepassword: A onepassword reference from which to retrieve
        the client ID. Note: the user will be prompted to login, if they have
        not already done so, unless a `OP_SERVICE_ACCOUNT_TOKEN` environment
        variable has been set, and/or both both an `OP_CONNECT_HOST` and
        `OP_CONNECT_TOKEN` environment variable have been set.
        client_secret_onepassword: A onepassword reference from which to retrieve
        the client secret. Note: the user will be prompted to login, if they have
        not already done so, unless a `OP_SERVICE_ACCOUNT_TOKEN` environment
        variable has been set, and/or both both an `OP_CONNECT_HOST` and
        `OP_CONNECT_TOKEN` environment variable have been set.
        client_id_environment_variable: An environment variable from which
        the client ID may be retrieved
        client_secret_environment_variable: An environment variable from which
        the client secret may be retrieved
    """
    return Client(
        oauth2_client_id=client_id,
        oauth2_client_secret=client_secret
    )


# Initialize an OAuth 2 Client
client: Client = get_client(
  client_id_databricks_secret=("client-scope", "client-id-key"),
  client_secret_databricks_secret=("client-scope", "client-secret-key"),
  client_id_onepassword="op://Vault Name/Client ID Item Name/username",
  client_secret_onepassword="op://Vault Name/Client Secret Item Name/credential",
  client_id_environment_variable="MY_APP_CLIENT_ID",
  client_secret_environment_variable="MY_APP_CLIENT_SECRET",
)
```