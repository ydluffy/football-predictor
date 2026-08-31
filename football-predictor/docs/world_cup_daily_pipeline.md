# 世界杯每日预测流水线

每日流水线把原本分散的步骤串成一个入口：

1. 导入雷速公开首页比赛数据
2. 匹配雷速比赛到 ESPN 世界杯赛程
3. 运行阵容调整版世界杯预测
4. 生成中文 Excel 预测日报
5. 创建赛前预测快照
6. 根据 ESPN scoreboard 生成复盘报告

预测日报现在包含让球胜平负三项概率：让胜、让平、让负，以及模型推断的让球线。

## 离线缓存模式

适合开发和本地复现，不重新下载 ESPN/雷速数据：

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_daily_pipeline.py `
  --as-of-date 2026-06-25 `
  --dry-run false `
  --node "C:\Users\YDluf\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" `
  --audit-output artifacts\pipeline\world_cup_daily_pipeline_2026-06-25.json
```

## 联网刷新模式

如果要刷新 ESPN 全量名单/首发和雷速首页：

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_daily_pipeline.py `
  --as-of-date 2026-06-25 `
  --refresh-espn true `
  --download-leisu true `
  --node "C:\Users\YDluf\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" `
  --audit-output artifacts\pipeline\world_cup_daily_pipeline_2026-06-25.json
```

注意：`--refresh-espn true` 会下载 scoreboard、球队名单和比赛摘要，耗时更长；网络环境受限时可能需要授权。

## 主要输出

- 预测 CSV：`artifacts/predictions/world_cup_lineup_adjusted_with_leisu_YYYY-MM-DD.csv`
- 预测审计：`artifacts/predictions/world_cup_lineup_adjusted_with_leisu_YYYY-MM-DD.json`
- 中文 Excel 日报：`outputs/world_cup_report/2026世界杯预测日报_YYYY-MM-DD.xlsx`
- 赛前快照：`artifacts/prediction_snapshots/world_cup_prediction_snapshot_YYYY-MM-DD.csv`
- 复盘明细：`artifacts/reviews/world_cup_review_ledger_YYYY-MM-DD.csv`
- 分组统计：`artifacts/reviews/world_cup_review_group_stats_YYYY-MM-DD.csv`
- 中文复盘：`artifacts/reviews/世界杯预测复盘_YYYY-MM-DD.md`
- 流水线审计：`artifacts/pipeline/world_cup_daily_pipeline_YYYY-MM-DD.json`

注意：赛前快照默认不覆盖。如果同一天已经生成过快照，复盘会继续使用旧快照，避免赛后污染预测记录。开发新字段时如需验证，可使用临时 `--snapshot-date` 单独跑复盘。

## 当前 2026-06-25 运行结果

本地离线缓存模式已跑通：

- 预测场次：21
- 已结算：2
- 待结算：19
- 胜平负命中率：50.0%
- 大小 2.5 命中率：50.0%

该日期样本已结算场次很少，主要用于验证流水线可运行，不用于判断模型表现。
