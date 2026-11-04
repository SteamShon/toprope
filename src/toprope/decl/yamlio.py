"""YAML loading with YAML 1.2 core-schema scalars and duplicate-key detection.

PyYAML follows YAML 1.1: `on`/`off`/`yes`/`no` are booleans, `12:30` is a sexagesimal int,
`0777` is octal, and duplicate keys silently overwrite. Declarations use `on:` as a key and
must surface typos, so they load with YAML 1.2 core rules: booleans are only `true`/`false`;
ints are decimal, `0o` octal or `0x` hex; floats have no sexagesimal form; duplicate keys
are errors.
"""

from __future__ import annotations

import re
from typing import Any

import yaml
from yaml.constructor import ConstructorError

_REPLACED = {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:int", "tag:yaml.org,2002:float",
             "tag:yaml.org,2002:value"}


class Yaml12Loader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):  # type: ignore[override]
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ConstructorError("while constructing a mapping", node.start_mark,
                                       f"found duplicate key {key!r}", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)

    def construct_yaml_int(self, node):  # type: ignore[override]
        v = self.construct_scalar(node).replace("_", "")
        if v.startswith(("0o", "+0o", "-0o")):
            return int(v.replace("0o", ""), 8)
        return int(v, 0) if v.lstrip("+-").startswith("0x") else int(v, 10)


# Copy the resolver table (do not mutate SafeLoader's), then add YAML 1.2 core rules.
Yaml12Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag not in _REPLACED]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
Yaml12Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))
Yaml12Loader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$"),
    list("-+0123456789"))
Yaml12Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
               r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"),
    list("-+0123456789."))
Yaml12Loader.add_constructor("tag:yaml.org,2002:int", Yaml12Loader.construct_yaml_int)


def load_yaml(text: str) -> Any:
    return yaml.load(text, Loader=Yaml12Loader)  # noqa: S506 - SafeLoader subclass
