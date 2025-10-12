from __future__ import annotations

import re
from pathlib import Path

from hatch.env.collectors.plugin.interface import EnvironmentCollectorInterface

ENV: Path = Path(__file__).parent / ".env"
PATTERN: re.Pattern = re.compile(
    r"""^([^\s=]+)=(?:[\s"']*)(.+?)(?:[\s"']*)$"""
)


class DotEnvCollectorInterface(EnvironmentCollectorInterface):
    """
    This collector loads environment variables from a .env file, if found
    """

    def finalize_environments(
        self, config: dict[str, dict]
    ) -> dict[str, dict]:
        env: dict[str, str] = {}
        with ENV.open(encoding="utf-8") as env_io:
            line: str
            for line in env_io:
                match: re.Match | None = PATTERN.match(line)
                if match is not None:
                    env[match.group(1)] = match.group(2)
        environment: dict[str, dict[str, str]]
        for environment in config.values():
            if "env-vars" not in environment:
                environment["env-vars"] = env
            else:
                environment["env-vars"].update(env)
        return config
