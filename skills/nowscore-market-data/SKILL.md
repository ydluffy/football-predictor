---
name: nowscore-market-data
description: 获取捷报竞彩场次与单场外盘赔率，并维护 The Odds API 无额度、无赛事路由或覆盖失败时的自动后备采集。适用于本足球预测项目中捷报/Nowscore 外盘补缺、影子对照和取数排障；不用于直接生成投注方案。
---

# 捷报外盘数据采集

在 `E:/ball-match-prediction-system/football-predictor` 工作。先确认当前竞彩扫描文件及销售日；不得用赛后网页的“即时”值回填赛前报价，也不得让未唯一映射或开赛后采集的行进入研究样本。

## 采集

运行 `scripts/capture_nowscore_market.py`。它以 `artifacts/data/sporttery_sales_window_scan_latest_confirm.json` 为场次清单，从 `cp.nowscore.com` 取销售日、场次号和捷报比赛 ID，再定向读取 `live.nowscore.com/odds/match/<id>.htm`。仅在场次号、球队别名及开赛时间都吻合时标记 `mapped`。技能运行环境如无法直接访问网页，可由浏览器另存原始 HTML 后用 `--cp-html` 与 `--odds-html-dir` 离线导入；离线文件缺少可核验的原始采集时间，默认只留档、不得进入赛前研究。

标准命令（在 `football-predictor` 目录）：

```powershell
.\.venv\Scripts\python.exe scripts\capture_nowscore_market.py --scan-json artifacts\data\sporttery_sales_window_scan_latest_confirm.json
```

可用 `--max-matches 3` 做小批次试采。输出在 `data/external/nowscore/snapshots/<销售日>_<UTC时间>/`：原始 HTML、`alignment.csv`、六类报价的 `quotes.csv`、与项目现有 `SNAPSHOT_COLUMNS` 兼容的当前亚洲让球 `outer_market.csv`、`audit.json`。原始文件以快照目录隔离，已有文件若内容不同立即报错。

## 验收与使用边界

- 检查 `audit.json` 的 `mapped_count`、`captured_match_count`、`failures`、`research_eligible_rows`；检查 `alignment.csv` 中 `needs_review`、`unmatched`、`ambiguous`，不得只报告成功数量。
- `quotes.csv` 同时存初指与即时指、亚洲让球／欧洲胜平负／大小球。亚洲与大小球网页水位按香港盘 `1 + 水位` 转成十进制赔率，同时保留原始值；欧洲胜平负原值已是十进制。若页面口径变化，先停用并核验，不要静默转换。
- `outer_market.csv` 只写当前亚洲让球报价。`captured_at` 必须严格早于 `kickoff`、映射唯一、价格有效才可 `eligible_for_research=true`。初指没有已验证的发布时间，不能当作当前采集时刻的独立赛前快照。
- 不直接写入正式预测、投注方案或结算台账；先在影子研究中计算覆盖率、时效、公司分歧及对照效果，再决定是否接入统一历史和模型。
- 项目的 `scripts/build_unified_outer_market_history.py` 已可读取这些快照，把亚洲让球行合并到统一外盘历史；它不会自动把捷报报价升级为模型特征或正式决策。
- 项目确认扫描与终版刷新在 The Odds API 为 `quota_insufficient`、`no_routed_sports`、`not_configured`、`source_failed`、`unmatched` 或 `partial` 时自动调用 `capture_on_external_failure`；检查扫描或终版审计里的 `nowscore_fallback`、`trigger_status`、`effective_status` 与覆盖数。后备取得合格数据时 `effective_status=available_via_nowscore`，但主来源失败状态仍保留。后备采集有时长上限且失败不阻断官方体彩流程；没有安全完整的外盘模型特征时，正式预测仍退回体彩市场基线。统一历史文件被占用时，待写结果进入 `artifacts/data/unified_outer_market_pending/`，不得声称主历史已经更新。
- `live.nowscore.com/2in1.aspx` 和 `info.nowscore.com` 的主体依赖动态加载。需要扩展赛程、赛果、球队统计或历史盘口时，先用浏览器验证具体页面和时间戳，再增设独立采集器。资料库赛后更新的累计统计只能按赛前日期重建；单公司“详”页的历史变盘时间序列目前未通过稳定性验证。

本技能只负责数据采集与审计。项目脚本已接入主外盘不可用时的自动后备；独立的 Codex 定时任务和写入正式模型并未因此启用。
