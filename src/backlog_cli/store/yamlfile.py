"""YAML at the store boundary only: safe load, stable dump.

Loading uses the libyaml based loader when PyYAML has it: same data, much
faster. Dumping stays on the pure Python dumper: the libyaml one folds long
quoted strings differently, and the written files must not change.
"""

from pathlib import Path

import yaml


class YamlFile:
    SCHEMA_VERSION = 1
    LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

    class Dumper(yaml.SafeDumper):
        def ignore_aliases(self, data: object) -> bool:
            return True

    @classmethod
    def load(cls, path: Path) -> dict:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=cls.LOADER)

    @classmethod
    def dump(cls, data: dict) -> str:
        return yaml.dump(
            data,
            Dumper=cls.Dumper,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
            width=120,
        )
