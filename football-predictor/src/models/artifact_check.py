from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models.artifact_manifest import ModelArtifactManifest, check_compatibility, read_manifest


@dataclass(frozen=True)
class ArtifactCheckResult:
    status: str
    warnings: list[str]
    details: dict[str, Any]


def check_model_artifact(*, artifact_path: str | Path, manifest_path: str | Path | None = None) -> ArtifactCheckResult:
    p = Path(artifact_path)
    if not p.exists():
        return ArtifactCheckResult(status="incompatible", warnings=[], details={"reason": "artifact_missing", "artifact_path": str(p)})

    mp = Path(manifest_path) if manifest_path is not None else p.with_suffix(".manifest.json")
    if not mp.exists():
        return ArtifactCheckResult(status="warning", warnings=["manifest_missing"], details={"reason": "manifest_missing", "artifact_path": str(p), "manifest_path": str(mp)})

    manifest = read_manifest(mp)
    if manifest is None:
        return ArtifactCheckResult(status="warning", warnings=["manifest_unreadable"], details={"reason": "manifest_unreadable", "artifact_path": str(p), "manifest_path": str(mp)})

    comp = check_compatibility(manifest)
    if comp.ok:
        return ArtifactCheckResult(status="ok", warnings=[], details={"reason": "ok", "artifact_path": str(p), "manifest_path": str(mp)})

    if comp.reason == "python_version_mismatch":
        return ArtifactCheckResult(status="incompatible", warnings=[], details={"reason": comp.reason, "artifact_path": str(p), "manifest_path": str(mp), **comp.details})

    return ArtifactCheckResult(status="warning", warnings=[comp.reason], details={"reason": comp.reason, "artifact_path": str(p), "manifest_path": str(mp), **comp.details})

