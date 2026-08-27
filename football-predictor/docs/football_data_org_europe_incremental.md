# football-data.org 欧洲七联赛增量数据

## 范围

统一导入英超 `PL`、西甲 `PD`、德甲 `BL1`、法甲 `FL1`、意甲 `SA`、荷甲 `DED`、葡超 `PPL`。数据用途限于赛程/开赛时间校验、赛果、积分榜、球队与阵容基础资料；中国体彩官方在售状态和赛前赔率始终是投注闸门的唯一依据。

## 每日增量

```powershell
.\.venv\Scripts\python.exe scripts\import_football_data_org_europe_incremental.py `
  --date-from 2026-08-15 --date-to 2026-08-17
```

默认抓取比赛及七项赛事积分榜。`--skip-standings` 可用于低配额快速校验；`--include-teams` 只在每月回顾或明确需要刷新阵容时启用。令牌只读取项目 `.env` 中的 `FOOTBALL_DATA_TOKEN`。

原始 JSON 按内容哈希写入 `data/external/football_data_org_europe/raw/`，不可覆盖；规范化快照写入 `snapshots/`，累计历史写入 `*_history.csv`。`matches_latest.csv` 始终从累计历史按场次取最新版本，不会被窄日期窗口清空。

`v2_incremental_results.csv` 仅包含完场标签和基础赛季字段，不含赛前体彩/外盘赔率，所以只能作为映射、补结果和覆盖审计输入。只有完成同场唯一映射、时间安全校验并补齐不可变赛前赔率后，才允许进入候选训练集；不得直接追加到生产 v2 训练数据。

## 体彩赛果后备

每日复盘先运行中国体彩官方赛果导入器。仅当官方赛果不可用时才运行：

```powershell
.\.venv\Scripts\python.exe scripts\import_football_data_org_results.py `
  --scan-json artifacts\data\sporttery_sales_window_scan_latest_confirm.json `
  --official-markets data\manual\sporttery_handicap_markets_YYYY-MM-DD_HHMM_confirm.csv `
  --output-csv artifacts\data\football_data_org_result_fallback_YYYY-MM-DD.csv `
  --mapping-output artifacts\data\football_data_org_result_mapping_YYYY-MM-DD.csv `
  --audit-output artifacts\data\football_data_org_result_fallback_YYYY-MM-DD.json
```

后备导入必须满足：比赛状态为 `FINISHED`、90 分钟比分完整、体彩与外部球队名称可归一、开赛时间误差不超过 15 分钟且唯一匹配。任何缺失或歧义都只写审计，不得结算。只有明确增加 `--ledger ... --review-output ...` 才会调用现有幂等复盘逻辑写回台账。

## 套餐降级

各端点按实际账号权限执行。积分榜、球队或阵容端点被拒绝时，本次审计标记 `partial` 和对应 feed，已经取得的比赛数据仍可归档；不得把权限失败解释为球队无阵容或当天无比赛。接口比分可能受套餐延迟影响，因此不能替代停售前的体彩赔率刷新。
