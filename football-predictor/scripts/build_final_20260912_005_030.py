import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-12"
NUMBERS = [f"{n:03d}" for n in range(5, 31)]
FINAL_MARKET = ROOT / "data/manual/sporttery_handicap_markets_2026-09-12_1832_confirm.csv"
BASE_MARKET = ROOT / "data/manual/sporttery_handicap_markets_2026-09-12_1106_confirm.csv"
PLAY_FILE = ROOT / "data/manual/sporttery_play_odds_2026-09-12_1832_confirm.csv"
SCAN_FILE = ROOT / "artifacts/data/sporttery_sales_window_scan_2026-09-12_1832_confirm.json"
REPORT = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-12_1845_005-030.md"
AUDIT = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-12_1845_005-030.json"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def f(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pick(mapping, count=1):
    usable = [(key, value) for key, value in mapping.items() if value is not None and value > 0]
    return sorted(usable, key=lambda item: item[1])[:count]


def label_spf(key):
    return {"H": "主胜", "D": "平", "A": "客胜"}[key]


def label_rq(key):
    return {"H": "让胜", "D": "让平", "A": "让负"}[key]


scan = json.loads(SCAN_FILE.read_text(encoding="utf-8"))
fixtures = {item["match_number"]: item for item in scan["fixtures"] if item["match_number"] in NUMBERS}


def is_target_row(row):
    number = row.get("match_number", "").zfill(3)
    fixture = fixtures.get(number)
    return bool(
        fixture
        and row.get("home_team") == fixture["home_team"]
        and row.get("away_team") == fixture["away_team"]
    )


final_rows = {
    row["match_number"].zfill(3): row
    for row in read_csv(FINAL_MARKET)
    if is_target_row(row)
}
base_rows = {
    row["match_number"].zfill(3): row
    for row in read_csv(BASE_MARKET)
    if is_target_row(row)
}
play_rows = [
    row for row in read_csv(PLAY_FILE)
    if is_target_row(row)
]
plays = {}
for row in play_rows:
    key = (row["match_number"].zfill(3), row["play_type"])
    plays.setdefault(key, {})[row["selection"]] = f(row["odds"])

cards = []
for number in NUMBERS:
    fixture = fixtures[number]
    row = final_rows.get(number, {
        "competition": fixture["competition"],
        "kickoff_time": fixture["kickoff"].replace("T", " ")[:16],
        "home_team": fixture["home_team"],
        "away_team": fixture["away_team"],
        "home_handicap": "",
    })
    old = base_rows.get(number, {})
    spf = {"H": f(row.get("spf_odds_home")), "D": f(row.get("spf_odds_draw")), "A": f(row.get("spf_odds_away"))}
    rq = {"H": f(row.get("rqspf_odds_home")), "D": f(row.get("rqspf_odds_draw")), "A": f(row.get("rqspf_odds_away"))}
    old_spf = {"H": f(old.get("spf_odds_home")), "D": f(old.get("spf_odds_draw")), "A": f(old.get("spf_odds_away"))}
    primary = pick(spf, 2)
    spf_available = bool(primary)
    if not primary:
        outcome_scores = {"H": [], "D": [], "A": []}
        for selection, odds in plays.get((number, "correct_score"), {}).items():
            if odds is None or ":" not in selection:
                continue
            try:
                home_goals, away_goals = [int(part) for part in selection.split(":")]
            except ValueError:
                continue
            outcome_scores["H" if home_goals > away_goals else "D" if home_goals == away_goals else "A"].append(odds)
        inferred = {key: min(values) if values else None for key, values in outcome_scores.items()}
        primary = pick(inferred, 2)
    rq_primary = pick(rq, 2)
    primary_key, primary_odds = primary[0] if primary else ("", None)
    defense_key, defense_odds = primary[1] if len(primary) > 1 else ("", None)
    old_value = old_spf.get(primary_key)
    delta = round(primary_odds - old_value, 2) if primary_odds is not None and old_value is not None else None
    if not spf_available:
        movement = "SPF/RQSPF未开，仅比分盘结构推断"
    elif delta is None:
        movement = "无可比基线"
    elif delta <= -0.08:
        movement = f"{label_spf(primary_key)}增强{delta:+.2f}"
    elif delta >= 0.08:
        movement = f"{label_spf(primary_key)}降温{delta:+.2f}"
    else:
        movement = f"主方向稳定{delta:+.2f}"
    handicap = row.get("home_handicap", "")
    rq_key, rq_odds = rq_primary[0] if rq_primary else ("", None)
    rq_def_key, rq_def_odds = rq_primary[1] if len(rq_primary) > 1 else ("", None)
    conflict = (
        (primary_key == "H" and handicap.startswith("-") and rq_key == "A")
        or (primary_key == "A" and handicap.startswith("+") and rq_key == "H")
    )
    if not spf_available:
        contrarian = f"胜负盘未开，结构推断只作低置信观察，防{label_spf(defense_key)}"
    elif conflict:
        contrarian = f"SPF与受让/穿盘撕裂，防{label_spf(defense_key)}或一球差"
    elif primary_odds is not None and primary_odds <= 1.45:
        contrarian = f"大热拥挤，邪修只防{label_spf(defense_key)}，不机械反买"
    elif delta is not None and delta >= 0.08:
        contrarian = f"主方向临场降温，防{label_spf(defense_key)}"
    else:
        contrarian = f"无强异象，保留{label_spf(defense_key)}作冷门分支"
    goals = pick(plays.get((number, "total_goals"), {}), 2)
    scores = pick(plays.get((number, "correct_score"), {}), 3)
    half_full = pick(plays.get((number, "half_full_time"), {}), 2)
    model_note = "历史候选但需赛事校准" if fixture.get("historical_model_coverage") else "无历史训练覆盖，市场锚定"
    intelligence = "无可核验伤停/首发映射"
    if number == "022":
        intelligence = "API-Football唯一映射：热刺6条可用性警报、埃弗顿1条；首发0，主队方向降一级"
    cards.append({
        "number": number,
        "competition": row["competition"],
        "kickoff": row["kickoff_time"],
        "home": row["home_team"],
        "away": row["away_team"],
        "handicap": handicap,
        "spf": spf,
        "spf_available": spf_available,
        "rq": rq,
        "primary": label_spf(primary_key),
        "primary_key": primary_key,
        "primary_odds": primary_odds,
        "defense": label_spf(defense_key),
        "defense_odds": defense_odds,
        "rq_primary": label_rq(rq_key) if rq_key else "未开",
        "rq_key": rq_key,
        "rq_odds": rq_odds,
        "rq_defense": label_rq(rq_def_key) if rq_def_key else "未开",
        "rq_defense_odds": rq_def_odds,
        "movement": movement,
        "contrarian": contrarian,
        "goals": goals,
        "scores": scores,
        "half_full": half_full,
        "model_note": model_note,
        "intelligence": intelligence,
        "confidence": "低" if not spf_available else ("中低" if conflict or number == "022" else ("中高" if primary_odds is not None and primary_odds <= 1.5 else "中等")),
    })


def fmt_choices(items, translator=lambda x: x):
    return "/".join(f"{translator(key)}@{value:.2f}" for key, value in items) if items else "未开"


spf_rank = sorted([card for card in cards if card["spf_available"] and card["primary_odds"]], key=lambda card: card["primary_odds"])
strong = spf_rank[:6]
value = [card for card in spf_rank if 1.60 <= card["primary_odds"] <= 2.20][:4]
hot = [card for card in spf_rank if card["primary_odds"] <= 1.55][:3]
rq_draw_rank = sorted(
    [card for card in cards if card["rq"].get("D")],
    key=lambda card: card["rq"]["D"],
)[:3]

schemes = []
if len(strong) >= 6:
    schemes += [
        {"name": "正道强势A", "selection": " × ".join(f"{c['number']}{c['primary']}@{c['primary_odds']:.2f}" for c in strong[:2]), "stake": 2, "type": "2串1影子"},
        {"name": "正道强势B", "selection": " × ".join(f"{c['number']}{c['primary']}@{c['primary_odds']:.2f}" for c in strong[2:4]), "stake": 2, "type": "2串1影子"},
        {"name": "正道强势C", "selection": " × ".join(f"{c['number']}{c['primary']}@{c['primary_odds']:.2f}" for c in strong[4:6]), "stake": 2, "type": "2串1影子"},
    ]
if len(value) >= 2:
    schemes.append({"name": "价值双选", "selection": " × ".join(f"{c['number']}{c['primary']}@{c['primary_odds']:.2f}" for c in value[:2]), "stake": 2, "type": "2串1影子"})
if hot:
    schemes.append({"name": "邪修反热门", "selection": " × ".join(f"{c['number']}{c['defense']}@{c['defense_odds']:.2f}" for c in hot), "stake": 2, "type": f"{len(hot)}串1影子"})
schemes.append({"name": "邪修让平", "selection": " × ".join(f"{c['number']}{c['handicap']}让平@{c['rq']['D']:.2f}" for c in rq_draw_rank), "stake": 2, "type": "3串1影子"})
balanced = sorted([card for card in cards if card["spf_available"]], key=lambda card: abs(card["spf"]["H"] - card["spf"]["A"]))[:2]
schemes.append({"name": "防冷复式", "selection": " × ".join(f"{c['number']}{c['primary']}/{c['defense']}" for c in balanced), "stake": 8, "type": "4注复式影子"})
goal_cards = [card for card in cards if card["goals"]][:3]
schemes.append({"name": "进球格局", "selection": " × ".join(f"{c['number']}进球{c['goals'][0][0]}/{c['goals'][1][0]}" for c in goal_cards), "stake": 16, "type": "8注复式影子"})

lines = [
    "# 2026-09-12 体彩005—030终版分析", "",
    "冻结时间：北京时间2026-09-12 18:45；005于20:00最早开赛，19:45硬锁。18:32重新抓取体彩SPF/RQSPF、总进球、比分和半全场，26场全部仍在售，终版门禁为`READY_FOR_FINAL_ANALYSIS`。001—004已开赛或停售，明确排除。", "",
    "数据边界：The Odds终版继续HTTP 401、0/26映射，失败快照排除；API-Football只唯一映射022热刺vs埃弗顿，最新记录为热刺6条、埃弗顿1条可用性警报，首发0。其余25场没有可归属的伤停或首发，不填写‘无伤停’。", "",
    "## 26场完整赛程与逐场预测", "",
    "|编号/时间/赛事|比赛|SPF正道|让球|邪修检查|进球|比分|半全场|信心|", "|---|---|---|---|---|---|---|---|---|",
]
for card in cards:
    spf_text = (f"{card['primary']}@{card['primary_odds']:.2f}，防{card['defense']}@{card['defense_odds']:.2f}；{card['movement']}" if card['spf_available'] else f"SPF未开；比分结构偏{card['primary']}，防{card['defense']}")
    rq_text = (f"{card['handicap']} {card['rq_primary']}@{card['rq_odds']:.2f}，防{card['rq_defense']}@{card['rq_defense_odds']:.2f}" if card['rq_odds'] is not None else "RQSPF未开")
    lines.append(
        f"|{card['number']} {card['kickoff'][11:]} {card['competition']}|{card['home']}—{card['away']}|{spf_text}|{rq_text}|{card['contrarian']}|{fmt_choices(card['goals'])}|{fmt_choices(card['scores'])}|{fmt_choices(card['half_full'])}|{card['confidence']}|"
    )

lines += ["", "## 逐场正邪依据与数据边界", ""]
for card in cards:
    lines += [
        f"### {card['number']} {card['home']} vs {card['away']}",
        (f"- 正道：{card['model_note']}；体彩主方向{card['primary']}@{card['primary_odds']:.2f}，防{card['defense']}@{card['defense_odds']:.2f}。{card['movement']}。" if card['spf_available'] else f"- 正道：{card['model_note']}；SPF未开，仅按比分赔率结构低置信推断{card['primary']}，防{card['defense']}，不提供伪造SPF赔率。"),
        (f"- 让球：主队{card['handicap']}，首选{card['rq_primary']}@{card['rq_odds']:.2f}，次选{card['rq_defense']}@{card['rq_defense_odds']:.2f}。" if card['rq_odds'] is not None else "- 让球：RQSPF未开，不给出伪造让球选择。"),
        f"- 邪修：{card['contrarian']}。赔率异象只用于降级、扩展或弃场，不直接等同赛果。",
        f"- 多玩法：总进球{fmt_choices(card['goals'])}；比分{fmt_choices(card['scores'])}；半全场{fmt_choices(card['half_full'])}。",
        f"- 情报：{card['intelligence']}。", "",
    ]

lines += [
    "## 冻结影子方案（本批不进正式台账）", "",
    "9月12日正式模拟台账已在14:00和16:30写满两组上限，本批无论门禁是否READY均不得新增正式方案。以下全部只作为明日复盘样本。", "",
    "|方案|类型|冻结选择|虚拟本金|", "|---|---|---|---:|",
]
for scheme in schemes:
    lines.append(f"|{scheme['name']}|{scheme['type']}|{scheme['selection']}|{scheme['stake']}元|")

lines += [
    "", "## 022伤停映射核验", "",
    "API-Football唯一映射到022热刺vs埃弗顿，比赛标识1557406、开赛22:30。18:34快照可见热刺侧X. Simons（膝）、D. Kulusevski（膝）、Richarlison（转会谈判）、M. Mudryk（脚踝）、W. Odobert（膝）、J. Maddison（撞伤）共6条可用性记录，埃弗顿侧C. Norgaard（伤病）1条；接口字段标记confirmed，但没有首发。由于其中包含‘转会谈判’而非纯伤病，本报告只把主队人员不确定性作为降级项，不把6条全部视为确定缺阵。", "",
    "## 风控与明日复盘", "",
    "- 26场中，SPF主方向、明确防守、让球首选/次选、进球双选、比分三选和半全场双选均已冻结。明日13:00按官方90分钟赛果逐场核实。",
    "- 每个影子方案按实际子注拆分投入、返奖、净收益和ROI；复式只命中部分子注时不得宣传为整组命中。",
    "- The Odds失败快照和25场未映射情报未进入模型；022伤停只降低信心，不替代赔率与基本面。",
    "- 本批生产台账新增0、正式模拟方案新增0、重复入账0。9月12日未获Supabase同步授权，仅本地落盘。",
]

REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
payload = {
    "schema_version": 1,
    "sales_day": DAY,
    "stage": "final",
    "scope": "005-030",
    "frozen_at": "2026-09-12T18:45:00+08:00",
    "official_captured_at": scan["scanned_at"],
    "gate": "READY_FOR_FINAL_ANALYSIS",
    "matches": 26,
    "external_odds": "http_401_mapped_0_of_26_excluded",
    "api_football": "mapped_1_of_26_match_022_absence_flags_7_visible_starters_0",
    "predictions": cards,
    "shadow_schemes": schemes,
    "formal_plans": [],
    "formal_plan_reason": "daily formal plan limit of two already reached by 14:00 and 16:30 batches",
    "production_ledger_write_performed": False,
    "production_ledger_rows_added": 0,
    "report": str(REPORT.relative_to(ROOT)).replace("\\", "/"),
    "review_due_at": "2026-09-13T13:00:00+08:00",
    "supabase_sync": "not_authorized_for_2026-09-12",
}
AUDIT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"matches": len(cards), "schemes": len(schemes), "report": payload["report"], "formal_plans": 0}, ensure_ascii=False))
