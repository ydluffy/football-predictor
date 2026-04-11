from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent.schemas import EvidenceBundle, MatchContext, VerificationResult


class VerifierBase(ABC):
    @abstractmethod
    def collect_evidence(self, match_context: MatchContext) -> EvidenceBundle: ...

    @abstractmethod
    def verify_local(self, bundle: EvidenceBundle) -> dict[str, Any]: ...

    @abstractmethod
    def verify_global(self, bundle: EvidenceBundle) -> dict[str, Any]: ...

    @abstractmethod
    def generate_result(
        self,
        *,
        bundle: EvidenceBundle,
        local_result: dict[str, Any],
        global_result: dict[str, Any],
    ) -> VerificationResult: ...

