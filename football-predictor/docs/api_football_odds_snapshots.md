# API-Football 赔率不可变快照

## 目标

把 API-Football 的亚洲让球赔率保存成可审计、不可覆盖的赛前历史，用于研究外盘精确四分之一盘口与体彩整数让球的差异。API 自带预测不进入该数据集。

## 标准调用

```powershell
.\.venv\Scripts\python.exe scripts\import_api_football_odds_snapshot.py `
  --scan-json artifacts\data\sporttery_sales_window_scan_latest_confirm.json `
  --date 2026-08-16
```

脚本先按北京时间日期一次取得赛程，再通过球队别名和开赛时间（默认容差15分钟）与当天全部体彩场次唯一匹配。只有唯一匹配的场次才请求赔率。需要限制单项赛事时可增加 `--league-id 140`。这样可以避开 Free 套餐无法按当前赛季参数查询的问题，并减少赛程请求次数。

## 输出

- `data/external/api_football_odds/raw/YYYY-MM-DD/<fixture_id>/`：原始 JSON，文件名包含抓取时间和内容哈希。
- `data/external/api_football_odds/snapshots/YYYY-MM-DD/`：每次全量标准化快照及对应 `_primary.csv`。
- `data/external/api_football_odds/history.csv`：跨时间累计历史，按 `record_id` 幂等追加。
- `artifacts/data/api_football_odds_snapshot_latest.json`：映射、额度、失败、赛前安全性和文件审计。

## 盘口口径

API 返回的同一数值下，`Home -0.25` 与 `Away -0.25` 是同一主队视角盘口的两边报价。标准化后保存为 `home_handicap=-0.25`、`away_handicap=+0.25`，不能把客队一侧再次解释成 `-0.25`。

每家机构可能同时返回许多替代盘。全量盘全部保留；主盘口候选取主客赔率最接近均衡的一条，并要求 `price_balance_score <= 0.5`。生产研究默认只读取 `eligible_for_primary_research=true`，避免把替代盘当作独立比赛重复训练。

## 安全闸门

- `captured_at` 必须带时区且严格早于开赛。
- 必须映射到唯一体彩 `match_id`。
- 盘口必须能规范化为0.25球步长。
- 原始响应和标准化快照不得覆盖；相同抓取时刻重复运行必须幂等。
- 映射失败、开赛后或盘口异常仍可归档，但不得进入研究或投注流程。

## 内外盘时间对齐

每次外盘快照完成后运行：

```powershell
.\.venv\Scripts\python.exe scripts\audit_inner_outer_market_alignment.py
```

审计先用体彩销售日和三位场次号构造稳定 `match_id`，再与外盘快照中已经唯一映射的 `match_id` 配对。相同 `match_id` 只能证明是同一场比赛；只有两边实际 `captured_at` 相差不超过30分钟，且两边都早于开赛，才标记 `time_aligned=true`。`provider_updated_at` 不能代替本地抓取时间。

输出 `artifacts/data/inner_outer_market_alignment_latest.csv/json`。CSV保留体彩整数让球、外盘精确四分之一盘口、两边赔率、抓取时间差及 `sporttery_minus_outer_handicap`。在至少300个不同比赛达到时间对齐前，`training_ready=false`，不得把盘口差值送入生产训练。
