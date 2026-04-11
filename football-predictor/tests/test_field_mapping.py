from __future__ import annotations

import pandas as pd
import pytest

from data.field_mapping import apply_field_mapping


def test_apply_field_mapping_keep_unmapped_true():
    df = pd.DataFrame({"MatchID": ["m1"], "HomeOdds": [2.1], "X": [1]})
    mapping = {"fields": {"MatchID": "match_id", "HomeOdds": "odds_home"}, "keep_unmapped": True, "strict": False}
    out = apply_field_mapping(df, mapping)
    assert {"match_id", "odds_home", "X"} <= set(out.columns)


def test_apply_field_mapping_keep_unmapped_false_drops_extra():
    df = pd.DataFrame({"MatchID": ["m1"], "HomeOdds": [2.1], "X": [1]})
    mapping = {"fields": {"MatchID": "match_id", "HomeOdds": "odds_home"}, "keep_unmapped": False, "strict": False}
    out = apply_field_mapping(df, mapping)
    assert list(out.columns) == ["match_id", "odds_home"]


def test_apply_field_mapping_missing_required_raises_when_strict():
    df = pd.DataFrame({"HomeOdds": [2.1]})
    mapping = {"fields": {"HomeOdds": "odds_home"}, "keep_unmapped": True, "strict": True}
    with pytest.raises(ValueError):
        apply_field_mapping(df, mapping)

