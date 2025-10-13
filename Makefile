SHELL := bash
.PHONY: docs
MINIMUM_PYTHON_VERSION := 3.10

# Create all environments
install:
	{ hatch --version || pipx install --upgrade hatch || python3 -m pip install --upgrade hatch ; } && \
	hatch env create default && \
	hatch env create docs && \
	hatch env create hatch-test && \
	echo "Installation complete"

# Re-create all environments, from scratch (no reference to pinned
# requirements)
reinstall:
	{ hatch --version || pipx install --upgrade hatch || python3 -m pip install --upgrade hatch ; } && \
	hatch env prune && \
	make && \
	make requirements

distribute:
	hatch build && hatch publish && rm -rf dist

# This will upgrade all requirements, and refresh pinned requirements to
# match. The same can be accomplished with `make reinstall`, but this
# runs faster, because environments are not recreated.
upgrade:
	hatch run dependence upgrade\
	 --include-pointer /tool/hatch/envs/default\
	 --include-pointer /project\
	 -aen all\
	 pyproject.toml && \
	hatch run docs:dependence upgrade\
	 --include-pointer /tool/hatch/envs/docs\
	 --include-pointer /project\
	 -aen all\
	 pyproject.toml && \
	hatch run hatch-static-analysis:dependence upgrade\
	 --include-pointer /tool/hatch/envs/hatch-static-analysis\
	 --include-pointer /project\
	 -aen all\
	 pyproject.toml && \
	hatch run hatch-test.py$(MINIMUM_PYTHON_VERSION):dependence upgrade\
	 --include-pointer /tool/hatch/envs/hatch-test\
	 --include-pointer /project\
	 -aen all\
	 pyproject.toml

# This will align project dependency versions with those installed in the
# default environment

# This will update dependencies to reflect the latest installed versions,
# and output the frozen requiements.txt file for use in job deployment
update:
	hatch run dependence update\
	 --include-pointer /tool/hatch/envs/default\
	 --include-pointer /project\
	 -aen all\
	 pyproject.toml && \
	hatch run docs:dependence update pyproject.toml --include-pointer /tool/hatch/envs/docs && \
	hatch run hatch-test.py$(MINIMUM_PYTHON_VERSION):dependence update pyproject.toml --include-pointer /tool/hatch/envs/hatch-test


# Apply formatting and enforce linting
format:
	hatch fmt --formatter && \
	hatch fmt --linter && \
	hatch run mypy && \
	echo "Format Successful!"

# Test & check linting/formatting (for local use only)
test:
	hatch fmt --check && hatch run mypy && hatch test -c

docs:
	hatch run docs:mkdocs build && \
	hatch run docs:mkdocs serve

# Cleanup untracked files
clean:
	git clean -f -e .vscode -e .idea -x . -e .env -e .devcontainer
