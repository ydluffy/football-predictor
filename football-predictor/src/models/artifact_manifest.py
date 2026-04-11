from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _pkg_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except Exception:
        return None


def _parse_major(version: str | None) -> int | None:
    if not version:
        return None
    s = str(version).strip()
    if not s:
        return None
    head = s.split(".", 1)[0]
    return int(head) if head.isdigit() else None


def _sha256(path: Path, *, max_bytes: int = 2_000_000) -> str | None:
    try:
        size = path.stat().st_size
    except Exception:
        return None
    if size > max_bytes:
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read())
    return h.hexdigest()


class ModelArtifactManifest(BaseModel):
    schema_version: str = "model_artifact_manifest_v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_type: str
    feature_version: str
    calibration_method: str
    artifact_path: str

    python_version: str
    platform: str
    numpy_version: str | None = None
    pandas_version: str | None = None
    sklearn_version: str | None = None
    lightgbm_version: str | None = None
    package_versions: dict[str, str | None] = Field(default_factory=dict)
    artifact_size_bytes: int | None = None
    artifact_sha256: str | None = None

    model_config = {"extra": "ignore"}


@dataclass(frozen=True)
class CompatibilityResult:
    ok: bool
    reason: str
    details: dict[str, Any]


class ModelArtifactLoadError(RuntimeError):
    def __init__(self, *, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = str(code)
        self.details = dict(details or {})


def build_manifest(*, model_type: str, feature_version: str, calibration_method: str, artifact_path: str | Path) -> ModelArtifactManifest:
    p = Path(artifact_path)
    pyv = ".".join(str(x) for x in sys.version_info[:3])
    pkgs = {
        "numpy": _pkg_version("numpy"),
        "pandas": _pkg_version("pandas"),
        "scikit-learn": _pkg_version("scikit-learn"),
        "lightgbm": _pkg_version("lightgbm"),
    }
    size = p.stat().st_size if p.exists() else None
    return ModelArtifactManifest(
        model_type=str(model_type),
        feature_version=str(feature_version),
        calibration_method=str(calibration_method),
        artifact_path=str(p),
        python_version=pyv,
        platform=str(sys.platform),
        numpy_version=pkgs.get("numpy"),
        pandas_version=pkgs.get("pandas"),
        sklearn_version=pkgs.get("scikit-learn"),
        lightgbm_version=pkgs.get("lightgbm"),
        package_versions=pkgs,
        artifact_size_bytes=int(size) if size is not None else None,
        artifact_sha256=_sha256(p),
    )


def write_manifest(*, path: str | Path, manifest: ModelArtifactManifest) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return p


def read_manifest(path: str | Path) -> ModelArtifactManifest | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return ModelArtifactManifest.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def check_compatibility(manifest: ModelArtifactManifest) -> CompatibilityResult:
    pyv = ".".join(str(x) for x in sys.version_info[:2])
    m_pyv = ".".join(str(x) for x in str(manifest.python_version).split(".")[:2])
    if pyv != m_pyv:
        return CompatibilityResult(ok=False, reason="python_version_mismatch", details={"required": m_pyv, "current": pyv})

    current = {
        "numpy": _pkg_version("numpy"),
        "pandas": _pkg_version("pandas"),
        "scikit-learn": _pkg_version("scikit-learn"),
        "lightgbm": _pkg_version("lightgbm"),
    }
    mismatches: dict[str, Any] = {}
    for name, required in (manifest.package_versions or {}).items():
        if name not in current:
            continue
        req_major = _parse_major(required)
        cur_major = _parse_major(current.get(name))
        if req_major is not None and cur_major is not None and req_major != cur_major:
            mismatches[name] = {"required": required, "current": current.get(name)}

    if mismatches:
        return CompatibilityResult(ok=False, reason="package_major_mismatch", details={"mismatches": mismatches})

    missing = [k for k, v in current.items() if v is None and (manifest.package_versions or {}).get(k) is not None]
    if missing:
        return CompatibilityResult(ok=False, reason="package_missing", details={"missing": missing})

    return CompatibilityResult(ok=True, reason="ok", details={"current": current})


def default_manifest_path_for_artifact(artifact_path: str | Path, manifest_path: str | Path | None = None) -> Path:
    if manifest_path is not None:
        return Path(manifest_path)
    p = Path(artifact_path)
    return p.with_suffix(".manifest.json")


def dump_load_error(e: BaseException) -> dict[str, Any]:
    return {"type": type(e).__name__, "message": str(e)}


def classify_deserialize_error(e: BaseException) -> tuple[str, dict[str, Any]]:
    msg = str(e)
    if isinstance(e, ModuleNotFoundError) and "numpy._core" in msg:
        return "numpy_pickle_incompatible", dump_load_error(e)
    if isinstance(e, ModuleNotFoundError):
        return "module_not_found", dump_load_error(e)
    if isinstance(e, AttributeError) and "Can't get attribute" in msg:
        return "pickle_attribute_missing", dump_load_error(e)
    return "deserialize_failed", dump_load_error(e)
