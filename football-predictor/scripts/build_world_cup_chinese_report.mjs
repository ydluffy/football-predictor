import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith("--")) continue;
    const key = item.slice(2);
    const value = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[i + 1] : "true";
    args[key] = value;
    if (value !== "true") i += 1;
  }
  return args;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];
    if (quoted) {
      if (ch === '"' && next === '"') {
        value += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        value += ch;
      }
      continue;
    }
    if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(value);
      value = "";
    } else if (ch === "\n") {
      row.push(value.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      value = "";
    } else {
      value += ch;
    }
  }
  if (value.length || row.length) {
    row.push(value.replace(/\r$/, ""));
    rows.push(row);
  }
  const headers = rows.shift() || [];
  return rows
    .filter((r) => r.some((v) => String(v).trim() !== ""))
    .map((r) => Object.fromEntries(headers.map((h, i) => [h, r[i] ?? ""])));
}

function num(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function pct(value) {
  return num(value);
}

function cleanId(value) {
  const text = String(value ?? "").trim();
  if (!text || text.toLowerCase() === "nan") return "";
  return text.replace(/\.0$/, "");
}

function zhResult(row) {
  const probs = [
    ["主胜", pct(row.adjusted_p_home)],
    ["平局", pct(row.adjusted_p_draw)],
    ["客胜", pct(row.adjusted_p_away)],
  ];
  probs.sort((a, b) => b[1] - a[1]);
  return probs[0][0];
}

function confidenceLabel(row) {
  const top = Math.max(pct(row.adjusted_p_home), pct(row.adjusted_p_draw), pct(row.adjusted_p_away));
  if (top >= 0.7) return "高";
  if (top >= 0.58) return "中高";
  if (top >= 0.48) return "中";
  return "低";
}

function totalsLabel(row) {
  return pct(row.over_2_5_probability) >= pct(row.under_2_5_probability) ? "偏大 2.5" : "偏小 2.5";
}

function handicapLabel(row) {
  if (row.handicap_recommended_result) {
    return `${row.handicap_label || ""} ${row.handicap_recommended_result}`.trim();
  }
  return "暂无让球盘";
}

function handicapSourceLabel(row) {
  if (row.handicap_line_source === "sporttery") return "体彩盘口";
  if (row.handicap_line_source === "model_inferred") return "模型估盘";
  return row.handicap_line_source || "";
}

function lineupLabel(row) {
  if (num(row.lineup_adjustment_active) > 0) return "双方首发确认，已启用阵容修正";
  if (num(row.home_lineup_confirmed) || num(row.away_lineup_confirmed)) return "部分首发确认";
  return "首发未完全确认";
}

function intelligenceLabel(row) {
  const count = num(row.leisu_intelligence_count);
  if (!num(row.leisu_public_match_linked)) return "未匹配";
  return count > 0 ? `${count} 条` : "已匹配，无情报数";
}

function completenessLabel(row) {
  const grade = String(row.data_completeness_grade || "");
  const score = num(row.data_completeness_score, 0);
  return grade ? `${grade} ${(score * 100).toFixed(0)}%` : "";
}

function sportteryCoverageLabel(audit) {
  const fixtures = num(audit.fixtures);
  const used = num(audit.sporttery_handicap_lines_used);
  const coverage = fixtures > 0 ? used / fixtures : 0;
  const status = audit.sporttery_handicap_quality_status || "unknown";
  return `${used}/${fixtures} (${(coverage * 100).toFixed(1)}%) ${status}`;
}

function sportteryCoverageMeaning(audit) {
  const fixtures = num(audit.fixtures);
  const used = num(audit.sporttery_handicap_lines_used);
  if (fixtures > 0 && used === fixtures) return "所有预测场次均使用真实体彩让球盘。";
  if (used > 0) return "部分场次使用真实体彩让球盘，未覆盖场次仍使用模型估盘。";
  return "未使用真实体彩让球盘，让球分析全部来自模型估盘。";
}

function enrich(row) {
  const totalGoals = num(row.expected_home_goals) + num(row.expected_away_goals);
  const topProb = Math.max(pct(row.adjusted_p_home), pct(row.adjusted_p_draw), pct(row.adjusted_p_away));
  return {
    ...row,
    match_id: cleanId(row.match_id),
    leisu_match_id: cleanId(row.leisu_match_id),
    match_name: `${row.home_team} vs ${row.away_team}`,
    result_pick: zhResult(row),
    confidence: confidenceLabel(row),
    top_probability: topProb,
    expected_total_goals: totalGoals,
    total_pick: totalsLabel(row),
    handicap_pick: handicapLabel(row),
    handicap_source_zh: handicapSourceLabel(row),
    lineup_status_zh: lineupLabel(row),
    leisu_intelligence_zh: intelligenceLabel(row),
    data_completeness_zh: completenessLabel(row),
  };
}

function writeBlock(sheet, startRow, startCol, matrix) {
  sheet.getRangeByIndexes(startRow, startCol, matrix.length, matrix[0].length).values = matrix;
}

function styleHeader(range) {
  range.format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
}

function styleTitle(range) {
  range.format = {
    fill: "#0F172A",
    font: { bold: true, color: "#FFFFFF", size: 16 },
  };
}

function addPredictionTable(sheet, rows, startRow = 8) {
  const headers = [
    "日期",
    "比赛",
    "胜平负建议",
    "信心",
    "主胜概率",
    "平局概率",
    "客胜概率",
    "预期总进球",
    "比分1",
    "比分1概率",
    "比分2",
    "比分2概率",
    "总进球判断",
    "大2.5概率",
    "小2.5概率",
    "让球盘",
    "让胜概率",
    "让平概率",
    "让负概率",
    "让球推荐",
    "盘口来源",
    "阵容状态",
    "雷速情报",
    "数据完整度",
    "雷速ID",
  ];
  const matrix = [
    headers,
    ...rows.map((r) => [
      r.date,
      r.match_name,
      r.result_pick,
      r.confidence,
      pct(r.adjusted_p_home),
      pct(r.adjusted_p_draw),
      pct(r.adjusted_p_away),
      num(r.expected_total_goals),
      r.top_score_1,
      pct(r.top_score_1_probability),
      r.top_score_2,
      pct(r.top_score_2_probability),
      r.total_pick,
      pct(r.over_2_5_probability),
      pct(r.under_2_5_probability),
      r.handicap_label,
      pct(r.handicap_home_win_probability),
      pct(r.handicap_draw_probability),
      pct(r.handicap_away_win_probability),
      r.handicap_pick,
      r.handicap_source_zh,
      r.lineup_status_zh,
      r.leisu_intelligence_zh,
      r.data_completeness_zh,
      r.leisu_match_id,
    ]),
  ];
  writeBlock(sheet, startRow, 0, matrix);
  const range = sheet.getRangeByIndexes(startRow, 0, matrix.length, headers.length);
  range.format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
  styleHeader(sheet.getRangeByIndexes(startRow, 0, 1, headers.length));
  sheet.tables.add(`A${startRow + 1}:Y${startRow + matrix.length}`, true, `PredictionTable${startRow}`);
  sheet.getRangeByIndexes(startRow + 1, 4, rows.length, 3).format.numberFormat = "0.0%";
  sheet.getRangeByIndexes(startRow + 1, 7, rows.length, 1).format.numberFormat = "0.00";
  sheet.getRangeByIndexes(startRow + 1, 9, rows.length, 1).format.numberFormat = "0.0%";
  sheet.getRangeByIndexes(startRow + 1, 11, rows.length, 1).format.numberFormat = "0.0%";
  sheet.getRangeByIndexes(startRow + 1, 13, rows.length, 2).format.numberFormat = "0.0%";
  sheet.getRangeByIndexes(startRow + 1, 16, rows.length, 3).format.numberFormat = "0.0%";
  return matrix.length;
}

function valueSignalLabel(value) {
  const text = String(value || "");
  if (text === "positive") return "正向分歧";
  if (text === "watch") return "观察";
  if (text === "probability_edge_only") return "仅概率分歧";
  if (text === "no_market") return "无市场赔率";
  return text;
}

function addMarketValueTable(sheet, rows, startRow = 4) {
  const valueRows = rows
    .filter((r) => r.handicap_line_source === "sporttery")
    .sort((a, b) => {
      const av = Math.max(num(a.spf_value_best_edge, -999), num(a.handicap_value_best_edge, -999));
      const bv = Math.max(num(b.spf_value_best_edge, -999), num(b.handicap_value_best_edge, -999));
      return bv - av;
    });
  const headers = [
    "日期",
    "比赛",
    "体彩编号",
    "让球盘",
    "胜平负价值方向",
    "胜平负Edge",
    "胜平负EV",
    "胜平负信号",
    "让球价值方向",
    "让球Edge",
    "让球EV",
    "让球信号",
    "模型主胜",
    "市场主胜",
    "模型平局",
    "市场平局",
    "模型客胜",
    "市场客胜",
  ];
  const matrix = [
    headers,
    ...valueRows.map((r) => [
      r.date,
      r.match_name,
      cleanId(r.sporttery_match_number),
      r.handicap_label,
      r.spf_value_best_result || "",
      r.spf_value_best_edge === "" ? "" : num(r.spf_value_best_edge, ""),
      r.spf_value_best_expected_value === "" ? "" : num(r.spf_value_best_expected_value, ""),
      valueSignalLabel(r.spf_value_signal),
      r.handicap_value_best_result || "",
      r.handicap_value_best_edge === "" ? "" : num(r.handicap_value_best_edge, ""),
      r.handicap_value_best_expected_value === "" ? "" : num(r.handicap_value_best_expected_value, ""),
      valueSignalLabel(r.handicap_value_signal),
      pct(r.adjusted_p_home),
      r.spf_market_home_probability === "" ? "" : num(r.spf_market_home_probability, ""),
      pct(r.adjusted_p_draw),
      r.spf_market_draw_probability === "" ? "" : num(r.spf_market_draw_probability, ""),
      pct(r.adjusted_p_away),
      r.spf_market_away_probability === "" ? "" : num(r.spf_market_away_probability, ""),
    ]),
  ];
  writeBlock(sheet, startRow, 0, matrix);
  const range = sheet.getRangeByIndexes(startRow, 0, matrix.length, headers.length);
  range.format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
  styleHeader(sheet.getRangeByIndexes(startRow, 0, 1, headers.length));
  sheet.tables.add(`A${startRow + 1}:R${startRow + matrix.length}`, true, "MarketValueTable");
  if (valueRows.length) {
    sheet.getRangeByIndexes(startRow + 1, 5, valueRows.length, 2).format.numberFormat = "0.0%";
    sheet.getRangeByIndexes(startRow + 1, 9, valueRows.length, 2).format.numberFormat = "0.0%";
    sheet.getRangeByIndexes(startRow + 1, 12, valueRows.length, 6).format.numberFormat = "0.0%";
  }
  headers.forEach((_, i) => {
    sheet.getRangeByIndexes(0, i, 1, 1).format.columnWidthPx = i === 1 ? 190 : 105;
  });
  return valueRows.length;
}

function addCompletenessTable(sheet, rows, startRow = 4) {
  const sorted = [...rows].sort(
    (a, b) => num(a.data_completeness_score, 0) - num(b.data_completeness_score, 0),
  );
  const headers = [
    "日期",
    "比赛",
    "完整度",
    "等级",
    "缺失项",
    "球员强度",
    "首发确认",
    "体彩盘口",
    "胜平负赔率",
    "让球赔率",
    "公开情报",
  ];
  const matrix = [
    headers,
    ...sorted.map((r) => [
      r.date,
      r.match_name,
      num(r.data_completeness_score, 0),
      r.data_completeness_grade || "",
      r.data_completeness_missing || "",
      num(r.data_component_player_strength, 0),
      num(r.data_component_confirmed_lineups, 0),
      num(r.data_component_sporttery_handicap, 0),
      num(r.data_component_spf_market_odds, 0),
      num(r.data_component_handicap_market_odds, 0),
      num(r.data_component_public_intelligence, 0),
    ]),
  ];
  writeBlock(sheet, startRow, 0, matrix);
  styleHeader(sheet.getRangeByIndexes(startRow, 0, 1, headers.length));
  sheet.getRangeByIndexes(startRow, 0, matrix.length, headers.length).format.borders = {
    preset: "all",
    style: "thin",
    color: "#D9E2F3",
  };
  sheet.tables.add(`A${startRow + 1}:K${startRow + matrix.length}`, true, "DataCompletenessTable");
  if (sorted.length) {
    sheet.getRangeByIndexes(startRow + 1, 2, sorted.length, 1).format.numberFormat = "0.0%";
    sheet.getRangeByIndexes(startRow + 1, 5, sorted.length, 6).format.numberFormat = "0.0%";
  }
  headers.forEach((_, i) => {
    sheet.getRangeByIndexes(0, i, 1, 1).format.columnWidthPx = i === 1 ? 190 : i === 4 ? 360 : 95;
  });
}

function setStandardWidths(sheet) {
  const widths = [90, 190, 90, 70, 80, 80, 80, 90, 70, 80, 70, 80, 95, 80, 80, 90, 80, 80, 80, 110, 90, 180, 90, 90, 85];
  widths.forEach((w, i) => {
    sheet.getRangeByIndexes(0, i, 1, 1).format.columnWidthPx = w;
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const reportDate = args["report-date"] || "2026-06-16";
  const predictionPath = path.join(
    ROOT,
    args.predictions || `artifacts/predictions/world_cup_lineup_adjusted_with_leisu_${reportDate}.csv`,
  );
  const auditPath = path.join(
    ROOT,
    args.audit || `artifacts/predictions/world_cup_lineup_adjusted_with_leisu_${reportDate}.json`,
  );
  const lineMovementPath = path.join(
    ROOT,
    args["line-movement"] || "data/manual/sporttery_handicap_line_movement_features.csv",
  );
  const outputDir = path.join(ROOT, args["output-dir"] || "outputs/world_cup_report");
  const csvText = await fs.readFile(predictionPath, "utf8");
  const audit = JSON.parse(await fs.readFile(auditPath, "utf8"));
  let lineMovementRows = [];
  try {
    lineMovementRows = parseCsv(await fs.readFile(lineMovementPath, "utf8"));
  } catch {
    lineMovementRows = [];
  }
  const rows = parseCsv(csvText).map(enrich).sort((a, b) => {
    const d = String(a.date).localeCompare(String(b.date));
    return d || String(a.match_id).localeCompare(String(b.match_id));
  });
  const topRows = [...rows].sort((a, b) => b.top_probability - a.top_probability).slice(0, 15);
  const linked = rows.filter((r) => num(r.leisu_public_match_linked));

  const workbook = Workbook.create();
  const overview = workbook.worksheets.add("预测总览");
  const highConfidence = workbook.worksheets.add("高信心场次");
  const details = workbook.worksheets.add("模型明细");
  const lineMovement = workbook.worksheets.add("盘口变化");
  const marketValue = workbook.worksheets.add("市场价值");
  const completeness = workbook.worksheets.add("数据完整度");
  const sources = workbook.worksheets.add("数据来源");

  for (const sheet of [overview, highConfidence, details, lineMovement, marketValue, completeness, sources]) {
    sheet.showGridLines = false;
  }

  overview.getRange("A1:X1").merge();
  overview.getRange("A1").values = [["2026 世界杯预测日报"]];
  styleTitle(overview.getRange("A1:X1"));
  overview.getRange("A2:X2").merge();
  overview.getRange("A2").values = [[`生成日期：${reportDate} | 数据截至：${audit.as_of_date} | 说明：概率来自本地 Elo/EWMA/泊松模型，已叠加可用阵容修正和雷速公开情报覆盖。`]];
  overview.getRange("A2:X2").format = { fill: "#EAF2F8", font: { color: "#1F2937" }, wrapText: true };
  writeBlock(overview, 3, 0, [
    ["可预测场次", rows.length, "启用阵容修正", audit.lineup_adjustment_active_matches, "雷速匹配预测", audit.leisu_linked_predictions, "高信心场次", rows.filter((r) => r.confidence === "高").length],
    ["首发确认队次", audit.confirmed_home_lineups + audit.confirmed_away_lineups, "球员强度数据", audit.player_strengths_loaded ? "已加载" : "未加载", "雷速情报场次", audit.leisu_predictions_with_intelligence, "平均球员强度置信", audit.mean_player_strength_confidence_in_predictions],
  ]);
  overview.getRange("A4:H5").format = { fill: "#F8FAFC", font: { bold: true } };
  addPredictionTable(overview, rows, 7);
  setStandardWidths(overview);
  overview.freezePanes.freezeRows(8);

  highConfidence.getRange("A1:X1").merge();
  highConfidence.getRange("A1").values = [["高信心场次 Top 15"]];
  styleTitle(highConfidence.getRange("A1:X1"));
  highConfidence.getRange("A2:X2").merge();
  highConfidence.getRange("A2").values = [["按三项概率中最高值排序。高信心不等于稳赚，只表示模型对胜平负方向分歧较小。"]];
  highConfidence.getRange("A2:X2").format = { fill: "#FEF3C7", wrapText: true };
  addPredictionTable(highConfidence, topRows, 4);
  setStandardWidths(highConfidence);
  highConfidence.freezePanes.freezeRows(5);

  const detailHeaders = [
    "date", "match_id", "home_team", "away_team", "result_pick", "confidence",
    "adjusted_p_home", "adjusted_p_draw", "adjusted_p_away", "expected_home_goals",
    "expected_away_goals", "top_score_1", "top_score_2", "over_2_5_probability",
    "under_2_5_probability", "handicap_label", "handicap_home_win_probability",
    "handicap_draw_probability", "handicap_away_win_probability",
    "handicap_recommended_result", "handicap_recommended_probability", "handicap_pick",
    "handicap_line_source",
    "lineup_status_zh",
    "leisu_public_match_linked", "leisu_match_id", "leisu_intelligence_count",
    "leisu_detail_url", "leisu_intelligence_url",
    "spf_market_home_probability", "spf_market_draw_probability",
    "spf_market_away_probability", "spf_value_best_result",
    "spf_value_best_edge", "spf_value_best_expected_value", "spf_value_signal",
    "handicap_market_home_probability", "handicap_market_draw_probability",
    "handicap_market_away_probability", "handicap_value_best_result",
    "handicap_value_best_edge", "handicap_value_best_expected_value",
    "handicap_value_signal",
    "data_completeness_score", "data_completeness_grade",
    "data_completeness_missing", "data_component_player_strength",
    "data_component_confirmed_lineups", "data_component_sporttery_handicap",
    "data_component_spf_market_odds", "data_component_handicap_market_odds",
    "data_component_public_intelligence",
  ];
  writeBlock(details, 0, 0, [
    detailHeaders,
    ...rows.map((r) => detailHeaders.map((h) => {
      if (h === "match_id" || h === "leisu_match_id") return cleanId(r[h]);
      if ([
        "adjusted_p_home", "adjusted_p_draw", "adjusted_p_away", "expected_home_goals",
        "expected_away_goals", "over_2_5_probability", "under_2_5_probability",
        "handicap_home_win_probability", "handicap_draw_probability",
        "handicap_away_win_probability", "handicap_recommended_probability",
        "spf_market_home_probability", "spf_market_draw_probability",
        "spf_market_away_probability", "spf_value_best_edge",
        "spf_value_best_expected_value", "handicap_market_home_probability",
        "handicap_market_draw_probability", "handicap_market_away_probability",
        "handicap_value_best_edge", "handicap_value_best_expected_value",
        "data_completeness_score", "data_component_player_strength",
        "data_component_confirmed_lineups", "data_component_sporttery_handicap",
        "data_component_spf_market_odds", "data_component_handicap_market_odds",
        "data_component_public_intelligence",
      ].includes(h)) return num(r[h]);
      return r[h] ?? "";
    })),
  ]);
  styleHeader(details.getRangeByIndexes(0, 0, 1, detailHeaders.length));
  details.tables.add(`A1:AZ${rows.length + 1}`, true, "ModelDetailsTable");
  details.getRangeByIndexes(1, 6, rows.length, 3).format.numberFormat = "0.0%";
  details.getRangeByIndexes(1, 9, rows.length, 2).format.numberFormat = "0.00";
  details.getRangeByIndexes(1, 13, rows.length, 2).format.numberFormat = "0.0%";
  details.getRangeByIndexes(1, 16, rows.length, 3).format.numberFormat = "0.0%";
  details.getRangeByIndexes(1, 20, rows.length, 1).format.numberFormat = "0.0%";
  details.getRangeByIndexes(1, 29, rows.length, 3).format.numberFormat = "0.0%";
  details.getRangeByIndexes(1, 33, rows.length, 2).format.numberFormat = "0.0%";
  details.getRangeByIndexes(1, 36, rows.length, 3).format.numberFormat = "0.0%";
  details.getRangeByIndexes(1, 40, rows.length, 2).format.numberFormat = "0.0%";
  details.getRangeByIndexes(1, 43, rows.length, 1).format.numberFormat = "0.0%";
  details.getRangeByIndexes(1, 46, rows.length, 6).format.numberFormat = "0.0%";
  details.freezePanes.freezeRows(1);
  detailHeaders.forEach((_, i) => {
    details.getRangeByIndexes(0, i, 1, 1).format.columnWidthPx = i >= 20 ? 260 : 120;
  });

  const movementHeaders = [
    "date", "match_id", "home_team", "away_team", "opening_home_handicap",
    "latest_home_handicap", "handicap_line_delta", "handicap_movement_direction",
    "favorite_movement", "opening_snapshot_type", "latest_snapshot_type",
    "opening_captured_at", "latest_captured_at", "snapshots",
  ];
  const movementRowsForSheet = lineMovementRows.length ? lineMovementRows : [{}];
  writeBlock(lineMovement, 0, 0, [
    movementHeaders,
    ...movementRowsForSheet.map((r) => movementHeaders.map((h) => {
      if ([
        "opening_home_handicap",
        "latest_home_handicap",
        "handicap_line_delta",
        "snapshots",
      ].includes(h)) return r[h] === undefined ? "" : num(r[h], "");
      return r[h] ?? "";
    })),
  ]);
  styleHeader(lineMovement.getRangeByIndexes(0, 0, 1, movementHeaders.length));
  lineMovement.tables.add(`A1:N${movementRowsForSheet.length + 1}`, true, "LineMovementTable");
  lineMovement.freezePanes.freezeRows(1);
  movementHeaders.forEach((_, i) => {
    lineMovement.getRangeByIndexes(0, i, 1, 1).format.columnWidthPx = i >= 10 ? 180 : 120;
  });

  marketValue.getRange("A1:R1").merge();
  marketValue.getRange("A1").values = [["市场价值分析"]];
  styleTitle(marketValue.getRange("A1:R1"));
  marketValue.getRange("A2:R2").merge();
  marketValue.getRange("A2").values = [["比较模型概率与体彩去水后的市场隐含概率。Edge=模型概率-市场概率，EV=模型概率×赔率-1。该页用于发现分歧，不等于自动投注建议。"]];
  marketValue.getRange("A2:R2").format = { fill: "#FEF3C7", wrapText: true };
  addMarketValueTable(marketValue, rows, 4);
  marketValue.freezePanes.freezeRows(5);

  completeness.getRange("A1:K1").merge();
  completeness.getRange("A1").values = [["数据完整度评分"]];
  styleTitle(completeness.getRange("A1:K1"));
  completeness.getRange("A2:K2").merge();
  completeness.getRange("A2").values = [["评分用于区分预测的数据厚度：历史模型、球员强度、首发、体彩盘口、赔率、公开情报都会影响等级。低分场次应优先补数据，不应过度解读。"]];
  completeness.getRange("A2:K2").format = { fill: "#EAF2F8", wrapText: true };
  addCompletenessTable(completeness, rows, 4);
  completeness.freezePanes.freezeRows(5);

  sources.getRange("A1:C1").merge();
  sources.getRange("A1:C1").values = [["数据来源与限制说明", null, null]];
  styleTitle(sources.getRange("A1:C1"));
  writeBlock(sources, 2, 0, [
    ["项目", "当前状态", "含义"],
    ["ESPN 世界杯赛程/名单", "已接入", "提供赛程、球队、球员名单、部分首发与赛后出场数据。"],
    ["雷速公开首页", `${linked.length} 场预测匹配`, "只使用公开网页可见信息：比赛 ID、中文队名、情报数量、链接。"],
    ["中国体彩让球盘", sportteryCoverageLabel(audit), sportteryCoverageMeaning(audit)],
    ["体彩盘口变化", `${lineMovementRows.length} 场`, "来自盘口历史快照的初盘/最新盘变化特征，用于复盘市场方向与模型判断是否一致。"],
    ["市场价值分析", "已接入", "将体彩赔率转成去水市场概率，并输出模型概率与市场概率差异、简单 EV 和分歧信号。"],
    ["数据完整度", `平均 ${(num(audit.mean_data_completeness_score, 0) * 100).toFixed(1)}%`, "用于判断每场预测依赖的数据是否足够厚，低完整度场次需要优先补伤停、首发、情报和盘口快照。"],
    ["阵容修正", `${audit.lineup_adjustment_active_matches} 场启用`, "只有双方确认 11 人首发时才启用，避免过度相信不完整阵容。"],
    ["模型口径", "Elo/EWMA/泊松 + 阵容修正", "适合做概率和比分分布估计，不是保证赛果。"],
  ]);
  styleHeader(sources.getRange("A3:C3"));
  sources.getRange("A3:C11").format.borders = { preset: "all", style: "thin", color: "#CBD5E1" };
  sources.getRange("A:C").format.wrapText = true;
  sources.getRange("A1").format.columnWidthPx = 180;
  sources.getRange("B1").format.columnWidthPx = 150;
  sources.getRange("C1").format.columnWidthPx = 560;

  await fs.mkdir(outputDir, { recursive: true });
  const overviewPreview = await workbook.render({ sheetName: "预测总览", range: "A1:X25", scale: 1, format: "png" });
  const highConfidencePreview = await workbook.render({ sheetName: "高信心场次", range: "A1:X22", scale: 1, format: "png" });
  const marketValuePreview = await workbook.render({ sheetName: "市场价值", range: "A1:R18", scale: 1, format: "png" });
  const completenessPreview = await workbook.render({ sheetName: "数据完整度", range: "A1:K22", scale: 1, format: "png" });
  const sourcesPreview = await workbook.render({ sheetName: "数据来源", range: "A1:C10", scale: 1, format: "png" });
  await fs.writeFile(
    path.join(outputDir, "preview_overview.png"),
    new Uint8Array(await overviewPreview.arrayBuffer()),
  );
  await fs.writeFile(
    path.join(outputDir, "preview_high_confidence.png"),
    new Uint8Array(await highConfidencePreview.arrayBuffer()),
  );
  await fs.writeFile(
    path.join(outputDir, "preview_market_value.png"),
    new Uint8Array(await marketValuePreview.arrayBuffer()),
  );
  await fs.writeFile(
    path.join(outputDir, "preview_data_completeness.png"),
    new Uint8Array(await completenessPreview.arrayBuffer()),
  );
  await fs.writeFile(
    path.join(outputDir, "preview_sources.png"),
    new Uint8Array(await sourcesPreview.arrayBuffer()),
  );
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    summary: "final formula error scan",
  });
  console.log(errors.ndjson);
  const check = await workbook.inspect({
    kind: "table",
    range: "预测总览!A1:X15",
    include: "values",
    tableMaxRows: 15,
    tableMaxCols: 24,
  });
  console.log(check.ndjson);
  const output = await SpreadsheetFile.exportXlsx(workbook);
  const outputPath = path.join(outputDir, `2026世界杯预测日报_${reportDate}.xlsx`);
  await output.save(outputPath);
  console.log(outputPath);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
