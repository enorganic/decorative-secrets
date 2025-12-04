SHELL := bash
.PHONY: docs
MINIMUM_PYTHON_VERSION := 3.10

# Create all environments
install:
	{ hatch --version || pipx install --upgrade hatch || python3 -m pip install --upgrade hatch ; } && \
	hatch env create default && \
	hatch env create docs && \
	hatch env create hatch-test && \
	hatch env create hatch-static-analysis && \
	echo "Installation complete"

# Re-create all environments, from scratch (no reference to pinned
# requirements)
reinstall:
	{ hatch --version || pipx install --upgrade hatch || python3 -m pip install --upgrade hatch ; } && \
	hatch env prune && \
	make && \
	make update

distribute:
	hatch build && hatch publish && rm -rf dist

# This will upgrade all dependencies to the latest compatible version.
# The same can be accomplished with `make reinstall`, but this
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
	 pyproject.toml && \
	hatch run hatch-test.py$(MINIMUM_PYTHON_VERSION):dependence upgrade\
	 --include-pointer /tool/hatch/envs/hatch-test\
	 --include-pointer /project\
	 pyproject.toml && \
	hatch run hatch-static-analysis:dependence upgrade\
	 --include-pointer /tool/hatch/envs/hatch-static-analysis\
	 --include-pointer /project\
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
	hatch run docs:dependence update\
	 --include-pointer /tool/hatch/envs/docs\
	 --include-pointer /project\
	 pyproject.toml && \
	hatch run hatch-test.py$(MINIMUM_PYTHON_VERSION):dependence update\
	 --include-pointer /tool/hatch/envs/hatch-test\
	 --include-pointer /project\
	 pyproject.toml && \
	hatch run hatch-static-analysis:dependence update\
	 --include-pointer /tool/hatch/envs/hatch-static-analysis\
	 --include-pointer /project\
	 pyproject.toml


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
