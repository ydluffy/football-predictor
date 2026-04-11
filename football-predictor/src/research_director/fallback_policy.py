from __future__ import annotations


ALLOWED_FALLBACK_POLICIES = {"strict", "graceful"}


def normalize_fallback_policy(value: str | None) -> str | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    if v not in ALLOWED_FALLBACK_POLICIES:
        raise ValueError(f"不支持的 fallback_policy: {value}")
    return v


def resolve_fallback_policy(*, workflow_name: str, context: dict) -> str:
    v = normalize_fallback_policy(context.get("fallback_policy"))
    if v:
        return v
    if str(workflow_name) == "daily_prediction":
        return "graceful"
    return "graceful"


def is_strict(policy: str) -> bool:
    return str(policy).strip().lower() == "strict"

