from __future__ import annotations

import pandas as pd

from world_cup.sporttery_markets import append_sporttery_market_history
from world_cup.sporttery_markets import build_sporttery_line_movement_features
from world_cup.sporttery_markets import build_sporttery_template_from_fixtures
from world_cup.sporttery_markets import find_sporttery_market
from world_cup.sporttery_markets import index_sporttery_markets
from world_cup.sporttery_markets import latest_sporttery_markets_from_history
from world_cup.sporttery_markets import load_sporttery_handicap_markets
from world_cup.sporttery_markets import parse_lottery_gov_spf_text
from world_cup.sporttery_markets import parse_sporttery_paste_text
from world_cup.sporttery_markets import parse_home_handicap
from world_cup.data import normalize_national_team


def test_parse_home_handicap_supports_common_sporttery_text():
    assert parse_home_handicap("-1") == -1.0
    assert parse_home_handicap("+1") == 1.0
    assert parse_home_handicap("主队让2球") == -2.0
    assert parse_home_handicap("主队受让1球") == 1.0
    assert parse_home_handicap("平手盘") == 0.0


def test_load_and_find_sporttery_handicap_market(tmp_path):
    path = tmp_path / "sporttery.csv"
    pd.DataFrame(
        [
            {
                "日期": "2026-06-25",
                "竞彩编号": "周四001",
                "主队": "Japan",
                "客队": "Sweden",
                "让球": "主队让1球",
                "来源": "sporttery_manual",
                "更新时间": "2026-06-25 10:00",
            }
        ]
    ).to_csv(path, index=False)

    markets = load_sporttery_handicap_markets(path)
    indexed = index_sporttery_markets(markets)
    found = find_sporttery_market(
        indexed,
        date="2026-06-25",
        home_team="Japan",
        away_team="Sweden",
    )

    assert found is not None
    assert found["home_handicap"] == -1.0
    assert found["match_number"] == "周四001"
    assert found["source"] == "sporttery_manual"


def test_load_sporttery_handicap_market_ignores_blank_rows(tmp_path):
    path = tmp_path / "sporttery.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-06-25",
                "home_team": "Japan",
                "away_team": "Sweden",
                "home_handicap": "",
            }
        ]
    ).to_csv(path, index=False)

    markets = load_sporttery_handicap_markets(path)

    assert markets.empty


def test_load_sporttery_handicap_market_preserves_three_digit_match_number(tmp_path):
    path = tmp_path / "sporttery.csv"
    path.write_text(
        "\n".join(
            [
                "date,match_number,home_team,away_team,home_handicap",
                "2026-06-26,055,Ecuador,Germany,+1",
            ]
        ),
        encoding="utf-8",
    )

    markets = load_sporttery_handicap_markets(path)

    assert markets.loc[0, "match_number"] == "055"


def test_find_sporttery_market_allows_one_day_kickoff_date_gap(tmp_path):
    path = tmp_path / "sporttery.csv"
    path.write_text(
        "\n".join(
            [
                "date,match_number,home_team,away_team,home_handicap",
                "2026-06-26,055,Ecuador,Germany,+1",
            ]
        ),
        encoding="utf-8",
    )
    markets = load_sporttery_handicap_markets(path)
    indexed = index_sporttery_markets(markets)

    found = find_sporttery_market(
        indexed,
        date="2026-06-25",
        home_team="Ecuador",
        away_team="Germany",
    )

    assert found is not None
    assert found["match_number"] == "055"
    assert found["home_handicap"] == 1.0


def test_parse_sporttery_paste_text_extracts_market_rows():
    text = "\n".join(
        [
            "周四001\tJapan\tSweden\t主队让1球",
            "周四002  Ecuador  Germany  平手盘",
        ]
    )

    rows = parse_sporttery_paste_text(text)

    assert rows == [
        {
            "match_number": "周四001",
            "home_team": "Japan",
            "away_team": "Sweden",
            "home_handicap": "主队让1球",
        },
        {
            "match_number": "周四002",
            "home_team": "Ecuador",
            "away_team": "Germany",
            "home_handicap": "平手盘",
        },
    ]


def test_parse_lottery_gov_spf_text_extracts_rendered_calculator_rows():
    text = "\n".join(
        [
            "周四 2026-06-25（共6场）",
            "编号\t赛事\t时间\t对阵\t让球\t胜平负赔率\t让球赔率\t支持率(胜/平/负)",
            "055\t世界杯\t06-26 04:00\t厄瓜多尔 vs 德国\t0 / +1\t5.20 / 4.95 / 1.36\t2.65 / 3.72 / 2.07\t13%/18%/69%",
            "058\t世界杯\t06-26 07:00\t日本 vs 瑞典\t0 / -1\t1.60 / 3.65 / 4.30\t2.75 / 3.35 / 2.15\t40%/27%/33%",
        ]
    )

    rows = parse_lottery_gov_spf_text(text, updated_at="2026-06-25 12:00")

    assert len(rows) == 2
    assert rows.loc[0, "date"] == "2026-06-26"
    assert rows.loc[0, "match_number"] == "055"
    assert rows.loc[0, "home_team"] == "厄瓜多尔"
    assert rows.loc[0, "away_team"] == "德国"
    assert rows.loc[0, "home_handicap"] == "+1"
    assert rows.loc[0, "spf_odds_home"] == 5.2
    assert rows.loc[0, "rqspf_odds_away"] == 2.07
    assert rows.loc[0, "support_away_pct"] == 69.0
    assert rows.loc[1, "home_handicap"] == "-1"
    assert normalize_national_team(rows.loc[0, "home_team"]) == "Ecuador"
    assert normalize_national_team(rows.loc[0, "away_team"]) == "Germany"


def test_parse_lottery_gov_spf_text_extracts_actual_block_layout():
    text = "\n".join(
        [
            "周四 2026-06-25 共6场比赛 (比赛编号日期：260625)[隐藏]",
            "周四",
            "055\t世界杯\t06-26",
            "04:00\t[E组3]厄瓜多尔 VS 德国[E组1]\t",
            "0",
            "+1",
            "5.204.951.36",
            "2.653.722.07",
            "同奖",
            "------",
            "------",
        ]
    )

    rows = parse_lottery_gov_spf_text(text)

    assert len(rows) == 1
    assert rows.loc[0, "date"] == "2026-06-26"
    assert rows.loc[0, "kickoff_time"] == "2026-06-26 04:00"
    assert rows.loc[0, "home_team"] == "厄瓜多尔"
    assert rows.loc[0, "away_team"] == "德国"
    assert rows.loc[0, "home_handicap"] == "+1"
    assert rows.loc[0, "spf_odds_home"] == 5.2
    assert rows.loc[0, "spf_odds_draw"] == 4.95
    assert rows.loc[0, "spf_odds_away"] == 1.36
    assert rows.loc[0, "rqspf_odds_away"] == 2.07


def test_build_sporttery_template_from_fixtures():
    fixtures = pd.DataFrame(
        [
            {
                "match_id": "760001",
                "date": "2026-06-25",
                "home_team": "Japan",
                "away_team": "Sweden",
            },
            {
                "match_id": "760002",
                "date": "2026-06-26",
                "home_team": "Mexico",
                "away_team": "Germany",
            },
        ]
    )

    out = build_sporttery_template_from_fixtures(
        fixtures,
        as_of_date="2026-06-25",
    )

    assert len(out) == 1
    assert out.loc[0, "match_id"] == "760001"
    assert out.loc[0, "home_handicap"] == ""
    assert out.loc[0, "source"] == "sporttery_manual"


def test_append_sporttery_market_history_and_select_latest(tmp_path):
    history_path = tmp_path / "history.csv"
    opening = pd.DataFrame(
        [
            {
                "date": "2026-06-25",
                "match_id": "760471",
                "match_number": "周四001",
                "home_team": "Japan",
                "away_team": "Sweden",
                "home_handicap": "主队让1球",
                "source": "sporttery_manual",
                "updated_at": "2026-06-25 10:00",
                "notes": "opening",
            }
        ]
    )
    closing = opening.assign(home_handicap="主队让2球", notes="closing")

    history = append_sporttery_market_history(
        history_path,
        opening,
        snapshot_type="opening",
        captured_at="2026-06-25T10:00:00+08:00",
    )
    history = append_sporttery_market_history(
        history_path,
        closing,
        snapshot_type="closing",
        captured_at="2026-06-25T18:00:00+08:00",
    )
    latest = latest_sporttery_markets_from_history(history)

    assert len(history) == 2
    assert history.iloc[0]["home_handicap"] == -1.0
    assert latest.loc[0, "home_handicap"] == "主队让2球"
    assert latest.loc[0, "snapshot_type"] == "closing"


def test_build_sporttery_line_movement_features(tmp_path):
    history_path = tmp_path / "history.csv"
    opening = pd.DataFrame(
        [
            {
                "date": "2026-06-25",
                "match_id": "760471",
                "match_number": "w001",
                "home_team": "Japan",
                "away_team": "Sweden",
                "home_handicap": "-1",
                "source": "sporttery_manual",
                "updated_at": "2026-06-25 10:00",
                "notes": "opening",
            }
        ]
    )
    closing = opening.assign(home_handicap="-2", notes="closing")
    history = append_sporttery_market_history(
        history_path,
        opening,
        snapshot_type="opening",
        captured_at="2026-06-25T10:00:00+08:00",
    )
    history = append_sporttery_market_history(
        history_path,
        closing,
        snapshot_type="closing",
        captured_at="2026-06-25T18:00:00+08:00",
    )

    movement = build_sporttery_line_movement_features(history)

    assert len(movement) == 1
    assert movement.loc[0, "opening_home_handicap"] == -1.0
    assert movement.loc[0, "latest_home_handicap"] == -2.0
    assert movement.loc[0, "handicap_line_delta"] == -1.0
    assert movement.loc[0, "handicap_movement_direction"] == "toward_home"
    assert movement.loc[0, "favorite_movement"] == "deeper"
