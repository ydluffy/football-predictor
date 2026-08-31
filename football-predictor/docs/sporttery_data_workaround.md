# 中国体彩盘口数据解决方案

中国体彩公开页面目前没有稳定、正式、适合程序直接调用的 API。本项目已有探针文件显示，直接请求体彩相关地址时会遇到 WAF 拦截或参数错误，因此不应把网页抓取当作核心生产链路。

## 推荐方案

采用“三层数据策略”：

1. 官方数据优先：人工从中国体彩网页/App/官方公告核对让球盘，填入 CSV。
2. 半自动兜底：如果后续浏览器侧可以导出页面表格，就保存成同样字段的 CSV，再走同一解析器。
3. 第三方校验：用雷速等公开数据做赛程、伤停、情报校验，但真实让球胜平负盘口仍以体彩字段为准。

## CSV 模板

模板文件：

`data/templates/sporttery_handicap_markets.csv`

支持字段：

- `date`：比赛日期，格式如 `2026-06-25`
- `match_number`：竞彩编号，例如 `周四001`
- `home_team`：主队，建议使用项目 fixtures 里的英文队名
- `away_team`：客队
- `home_handicap`：主队让球数，支持 `-1`、`+1`、`主队让1球`、`主队受让1球`、`平手盘`
- `source`：来源，例如 `sporttery_manual`
- `updated_at`：盘口记录时间
- `notes`：备注

项目内部约定：

- 负数表示主队让球，例如 `-1` 或 `主队让1球`
- 正数表示主队受让，例如 `+1` 或 `主队受让1球`
- `0` 或 `平手盘` 表示不让球

## 使用方式

把实际盘口保存为：

`data/manual/sporttery_handicap_markets_YYYY-MM-DD.csv`

然后运行预测脚本时传入：

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_lineup_adjusted.py `
  --as-of-date 2026-06-25 `
  --sporttery-markets data/manual/sporttery_handicap_markets_2026-06-25.csv
```

如果某场比赛找到了体彩盘口，输出字段 `handicap_line_source` 会是 `sporttery`；否则是 `model_inferred`。

每日流水线也支持同一份盘口文件：

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_daily_pipeline.py `
  --as-of-date 2026-06-25 `
  --sporttery-markets data/manual/sporttery_handicap_markets_2026-06-25.csv `
  --dry-run false `
  --node "C:\Users\YDluf\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" `
  --audit-output artifacts\pipeline\world_cup_daily_pipeline_2026-06-25.json
```

流水线审计会记录：

- `sporttery_markets`：本次传入的盘口文件
- `sporttery_markets_loaded`：预测脚本是否成功加载盘口文件
- `sporttery_handicap_lines_used`：有多少场比赛使用了体彩盘口

## 为什么这样做

这条路线牺牲了一点自动化，但换来稳定性、可追溯和合规边界更清晰。预测模型最怕的是“看起来自动，实际数据悄悄错了”。盘口数据宁可少一点，也要每条都知道从哪里来、什么时候更新、是否能复盘。
