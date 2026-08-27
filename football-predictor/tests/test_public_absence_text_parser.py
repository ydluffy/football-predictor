from __future__ import annotations

from world_cup.public_absence_text_parser import infer_absence_status
from world_cup.public_absence_text_parser import parse_structured_absence_text
from world_cup.public_absence_text_parser import parse_team_news_text


def test_structured_transfermarkt_style_text_parses_to_intelligence():
    text = """
    Germany | Player A | injury | hamstring injury | https://www.transfermarkt.com/a
    Argentina | Player B | suspension | red card suspension | https://www.transfermarkt.com/b
    """

    rows = parse_structured_absence_text(
        text,
        date="2026-06-27",
        source="transfermarkt",
    )

    assert len(rows) == 2
    assert set(rows["status"]) == {"injured", "suspended"}
    assert set(rows["source"]) == {"transfermarkt"}
    assert rows["confidence"].min() == 0.8


def test_sports_mole_team_news_text_parses_parenthesized_absences():
    text = """
    Germany: Player A (hamstring injury); Player B (late fitness test)
    Argentina: Player C (suspended after red card)
    """

    rows = parse_team_news_text(
        text,
        date="2026-06-27",
        source="sports_mole",
        source_url="https://www.sportsmole.co.uk/football/team-news",
    )

    assert len(rows) == 3
    assert rows.loc[rows["player"].eq("Player A"), "status"].iloc[0] == "injured"
    assert rows.loc[rows["player"].eq("Player B"), "status"].iloc[0] == "doubtful"
    assert rows.loc[rows["player"].eq("Player C"), "status"].iloc[0] == "suspended"
    assert rows["source_url"].str.contains("sportsmole").all()


def test_infer_absence_status_handles_common_terms():
    assert infer_absence_status("red card ban") == "suspended"
    assert infer_absence_status("late fitness test") == "doubtful"
    assert infer_absence_status("flu") == "illness"
    assert infer_absence_status("unknown detail") == "unknown"
