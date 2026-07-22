# Contributing to decorative-secrets

## For Enorganic Contributors and Code Owners

1.  Clone and Install

    To install this project for development of *this library*,
    clone this repository (replacing "~/Code", below, with the directory
    under which you want your project to reside), then run `make`:

    ```bash
    cd ~/Code && \
    git clone\
    https://github.com/enorganic/decorative-secrets.git decorative-secrets && \
    cd decorative-secrets && \
    make
    ```

2.  Create a new branch for your changes (replacing "descriptive-branch-name"
    with a *descriptive branch name*, and replacing *feature* with *bugfix*
    if the branch addresses a bug):

    ```shell
    git branch feature/descriptive-branch-name
    ```

3.  Make some changes.
4.  Format and lint your code:

    ```shell
    make format
    ```

5.  Test your changes:

    ```shell
    make test
    ```

6.  Push your changes and create a pull request.

## For Everyone Else

If you are not a contributor on this project, you can still create pull
requests, however you will need to fork this project, push changes
to your fork, and create a pull request from your forked repository.

## Conventions

- Annotate local variables explicitly, not just function signatures —
  see any module under `src/decorative_secrets/` for examples.
- Tests exercising a real external resource (Databricks CLI/workspace,
  1Password CLI/vault/Connect, Homebrew, WinGet, network installers) must
  be genuine integration tests against the real thing — no mocking those
  systems. See the `databricks_env`/`onepassword_vault` fixtures in
  `tests/conftest.py`. These tests depend on live, interactive CLI
  sessions (e.g. `op`'s biometric-unlock desktop integration), so an
  occasional transient failure unrelated to your change (a `signin`
  round-trip that needed a moment to authorize) is possible — re-run
  before assuming a regression.
- Save specs to `docs/superpowers/specs/YYYY-MM-DD-<branch>-design.md` and
  implementation plans to `docs/superpowers/plans/YYYY-MM-DD-<branch>.md`.
  When coding with an agent, this is _required_ (for transparency of
  instruction)—otherwise, use your discretion.
