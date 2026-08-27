from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
LOCK_PATH = PROJECT_ROOT / "requirements.txt"
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")
_LOCKED_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\]+)")


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared_names() -> set[str]:
    with PYPROJECT_PATH.open("rb") as stream:
        config = tomllib.load(stream)
    project = config["project"]
    requirements = list(project.get("dependencies", []))
    requirements.extend(project.get("optional-dependencies", {}).get("dev", []))
    names: set[str] = set()
    for requirement in requirements:
        match = _NAME_PATTERN.match(str(requirement))
        if match is None:
            raise ValueError(f"unsupported dependency declaration: {requirement}")
        names.add(_normalize_name(match.group(0)))
    return names


def _locked_names() -> set[str]:
    if not LOCK_PATH.exists():
        raise FileNotFoundError(f"missing lock file: {LOCK_PATH}")
    names: set[str] = set()
    for line in LOCK_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith(("#", " ", "--")):
            continue
        match = _LOCKED_PATTERN.match(line)
        if match is None:
            raise ValueError(f"lock entry is not exactly pinned: {line}")
        names.add(_normalize_name(match.group(1)))
    return names


def main() -> int:
    declared = _declared_names()
    locked = _locked_names()
    missing = sorted(declared - locked)
    if missing:
        print("requirements.txt is missing declared dependencies:", file=sys.stderr)
        for name in missing:
            print(f"- {name}", file=sys.stderr)
        print("Run: ..\\scripts\\project.ps1 python-lock", file=sys.stderr)
        return 1
    print(f"Dependency lock is valid ({len(locked)} exact packages, all direct dependencies present).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
