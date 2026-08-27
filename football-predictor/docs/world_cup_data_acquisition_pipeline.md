# 世界杯数据获取流水线

本项目目前支持三层数据获取方式，按可靠性和自动化程度组合使用。

## 1. 中国体彩官网自动抓取

使用本机浏览器渲染中国体彩竞彩足球胜平负/让球胜平负计算器页面：

```powershell
.\.venv\Scripts\python.exe scripts\refresh_lottery_gov_spf.py --date 2026-06-26
```

输出：

- `data/manual/sporttery_handicap_markets_YYYY-MM-DD.csv`
- `data/external/lottery_gov_zqspf_rendered.txt`

可选写入盘口历史：

```powershell
.\.venv\Scripts\python.exe scripts\refresh_lottery_gov_spf.py --date 2026-06-26 --append-history true --snapshot-type latest
```

## 2. 每日流水线自动刷新体彩

每日预测可以直接自动抓取体彩，再进入预测、盘口变化、Excel 日报和赛后复盘：

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_daily_pipeline.py --as-of-date 2026-06-25 --refresh-sporttery true --sporttery-date 2026-06-26
```

参数说明：

- `--as-of-date`：模型预测基准日期，按本地 fixture 日期。
- `--sporttery-date`：体彩官网开赛日期。跨午夜比赛经常需要比 `as-of-date` 晚一天。
- `--refresh-sporttery true`：先访问 `lottery.gov.cn`，生成体彩盘口 CSV。
- `--sporttery-quality-mode warn|fail|off`：控制盘口覆盖率不足时是警告还是中止。

## 3. 人工粘贴兜底

如果官网页面结构变化或本地浏览器无法访问，可以使用体彩盘口编辑器或文本导入脚本。

文本导入：

```powershell
.\.venv\Scripts\python.exe scripts\import_lottery_gov_spf_text.py --input data\external\lottery_gov_zqspf_rendered.txt --date 2026-06-26
```

编辑器：

```text
GET /world-cup/sporttery/editor
```

支持复制多行：

```text
周四001    Japan    Sweden    主队让1球
```

## 当前建议

常规赛前流程：

1. 先运行 `run_world_cup_daily_pipeline.py --refresh-sporttery true`。
2. 如果体彩覆盖率过低，检查 `data/external/lottery_gov_zqspf_rendered_*.txt`。
3. 必要时用编辑器或 `import_lottery_gov_spf_text.py` 手工兜底。
4. 保留历史快照，用 `build_sporttery_line_movement_features.py` 生成盘口变化特征。

这套方式不依赖扣子或其他外部 agent，核心能力在本地项目内闭环。
