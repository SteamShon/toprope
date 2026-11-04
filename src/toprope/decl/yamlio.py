"""YAML loading with YAML 1.2 booleans.

PyYAML follows YAML 1.1, where `on`, `off`, `yes`, `no`, `y` and `n` are booleans. The schema
uses `on:` as a key (invariants), so declarations are loaded with only `true`/`false` as
booleans, as YAML 1.2 specifies.
"""

from __future__ import annotations

import re
from typing import Any

import yaml


class Yaml12Loader(yaml.SafeLoader):
    pass


Yaml12Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:bool"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
Yaml12Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def load_yaml(text: str) -> Any:
    return yaml.load(text, Loader=Yaml12Loader)  # noqa: S506 - SafeLoader subclass
