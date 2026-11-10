# AGENTS.md

This is a python project configured in `pyproject.toml`.

Canonical commands may be found in the `Makefile`.

Use `make` targets when available for an operation. For example—to upgrade
dependencies, always use `make upgrade`. To run *all* tests, use `make test`
(to run individual tests use `hatch test`).

Always use `hatch run` rather than invoking the underlying virtual environment
directly.

Read `mkdocs.yaml` to discover project documentation.

## Human Controlled Changes

Every tracked-file change in this repository requires step-by-step human
confirmation. No plan, skill, or prior prompt may waive this workflow.

### Change Checkpoints

1.  One "change" may encompass more than one file, or non-contiguous sections
    of a file, only to the degree that all changes are intrinsically
    interdependent.
2.  The primary agent applies the change. Sub-agents may not make tracked-file
    changes.
3.  The human views the entire change set, optionally revises it, and stages
    the change either manually or through a separate, explicit request to
    the agent.
4.  The human explicitly confirms review and staging before authorizing
    the next tracked-file change.
