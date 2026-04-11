from __future__ import annotations

from agent.mock_verifier import MockVerifier
from agent.schemas import MatchContext


def test_mock_verifier_generates_risk_flags_and_result():
    verifier = MockVerifier(line_move_abs_threshold=0.2)
    mc = MatchContext(
        match_id="m1",
        league="EPL",
        odds_home=None,
        odds_draw=3.2,
        odds_away=4.0,
        injury_flag=1,
        line_move=0.35,
    )
    bundle = verifier.collect_evidence(mc)
    local = verifier.verify_local(bundle)
    global_ = verifier.verify_global(bundle)
    result = verifier.generate_result(bundle=bundle, local_result=local, global_result=global_)

    assert result.match_id == "m1"
    assert "injury_risk" in result.risk_flags
    assert "line_move_risk" in result.risk_flags
    assert "data_quality_risk" in result.risk_flags
    assert result.manual_review_required is True
    assert 0.0 <= result.source_confidence <= 1.0


def test_match_context_accepts_odds_snapshot_fields_and_extra_t_fields():
    mc = MatchContext(
        match_id="m1",
        odds_home_open=2.0,
        odds_home_last=1.9,
        odds_draw_t1=3.1,
        odds_draw_t2=3.2,
    )
    assert mc.match_id == "m1"
