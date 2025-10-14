# Command Line Interface

This package is primarily intended for use as a library, however exposes a
handful of utility commands for shell use.

```console
$ decorative-secrets -h
Usage:
  decorative-secrets <secret-manager> <command> [options]

Secret Managers:
  databricks
  onepasswor
```

## decorative-secrets databricks

```console
$ decorative-secrets databricks -h
Usage:
  decorative-secrets databricks <command> [options]

Commands:
  install
  get
```

## decorative-secrets databricks get

```console
$ decorative-secrets databricks get -h
usage: decorative-secrets databricks get
       [-h] [--host HOST] [-cid CLIENT_ID]
       [-cs CLIENT_SECRET] [-t TOKEN] [-p PROFILE]
       scope key

Get a secret from Databricks

positional arguments:
  scope
  key

options:
  -h, --help            show this help message and
                        exit
  --host HOST           A Databricks workspace
                        host URL
  -cid CLIENT_ID, --client-id CLIENT_ID
                        A Databricks OAuth2 Client
                        ID
  -cs CLIENT_SECRET, --client-secret CLIENT_SECRET
                        A Databricks OAuth2 Client
                        Secret
  -t TOKEN, --token TOKEN
                        A Databricks Personal
                        Access Token
  -p PROFILE, --profile PROFILE
                        A Databricks Configuration
                        Profile$
```

## decorative-secrets databricks install

```console
$ decorative-secrets databricks install -h
usage: decorative-secrets databricks install [-h]

Install the Databricks CLI

options:
  -h, --help  show this help message and exit
```

## decorative-secrets onepassword

```console
$ decorative-secrets onepassword -h        
Usage:
  decorative-secrets onepassword <command> [options]

Commands:
  install
  get
```

### decorative-secrets onepassword get

```console
$ decorative-secrets onepassword get -h
usage: decorative-secrets onepassword get
       [-h] [--account ACCOUNT] [-t TOKEN]
       [--host HOST]
       reference

Get a secret from 1Password

positional arguments:
  reference

options:
  -h, --help            show this help message and
                        exit
  --account ACCOUNT     Which 1Password account to
                        use
  -t TOKEN, --token TOKEN
                        A 1Password Service
                        Account Token
  --host HOST           A 1Password Connect Host
                        URL
```

### decorative-secrets onepassword install

```console
$ decorative-secrets onepassword install -h
usage: decorative-secrets onepassword install [-h]

Install the 1Password CLI

options:
  -h, --help  show this help message and exit
```



