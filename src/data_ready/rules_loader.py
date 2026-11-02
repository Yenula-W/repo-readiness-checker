"""Load target rule files (YAML). New repositories are data, not code."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Dict, List, Optional

import yaml

RULES_DIR = Path(__file__).parent / "rules"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def available_targets(extra_dir: Optional[Path] = None) -> List[str]:
    dirs = [RULES_DIR] + ([extra_dir] if extra_dir else [])
    names = set()
    for d in dirs:
        for p in d.glob("*.yaml"):
            if not p.stem.startswith("_"):
                names.add(p.stem)
    return sorted(names)


def _find(name: str, extra_dir: Optional[Path]) -> Path:
    candidate = Path(name)
    if candidate.suffix in (".yaml", ".yml") and candidate.exists():
        return candidate
    for d in ([extra_dir] if extra_dir else []) + [RULES_DIR]:
        p = d / f"{name}.yaml"
        if p.exists():
            return p
    raise KeyError(
        f"Unknown target '{name}'. Available: {', '.join(available_targets(extra_dir))}"
    )


def load_target(name: str, extra_dir: Optional[Path] = None) -> Dict:
    """Load a target by id or path, resolving `extends` chains."""
    path = _find(name, extra_dir)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parent = data.pop("extends", None)
    if parent:
        data = _deep_merge(load_target(parent, extra_dir), data)
    data.setdefault("id", path.stem)
    return data
