# 捷报（cp.nowscore.com）接口化说明（2026-10-21）

本文记录 2026-10-21 落地的「增量式」捷报接入：**现有 17 家赔率页链路完全不动**，
新增三个盘口 XML 接口作为页面抓取失败场次的兜底，新增变盘历史接口用于采集落库。

- 解析层：`src/data/nowscore_market.py`
- 采集层：`scripts/capture_nowscore_market.py`
- 同步层：`scripts/run_controller_data_sync.py` → `web/src/app/api/automation/sync-market/route.ts`
- 落库：`supabase/migrations/add_fixture_market_intel.sql`（`odds_price_changes`）

## 1. 接口清单

| 用途 | URL | 解析函数 |
| --- | --- | --- |
| 竞彩赛程页（原有链路） | `https://cp.nowscore.com/` | `parse_cp_page` |
| 赔率页（原有链路） | `https://live.nowscore.com/odds/match/{id}.htm` | `parse_odds_page` |
| 单一公司详情页（原有链路） | `https://live.nowscore.com/odds/3in1Odds.aspx?companyid={公司ID}&id={matchId}` | `parse_odds_page` |
| 亚盘兜底 | `https://cp.nowscore.com/data/yp101.xml?x=1` | `parse_asian_xml` |
| 大小球兜底 | `https://cp.nowscore.com/data/dx101.xml?x=1` | `parse_totals_xml` |
| 欧赔兜底 | `https://cp.nowscore.com/data/op101.xml?x=1` | `parse_h2h_xml` |
| 变盘历史 | `https://cp.nowscore.com/handle/odds.aspx?cmd=ypchange&oddsID={oddsId}&turn=1` | `parse_change_table` |

抓取路径由 `capture_nowscore_market.CP_FEEDS` / `CHANGE_URL` 常量集中定义；
`--odds-html-dir` 离线模式（`odds_html_dir is not None`）下不请求任何 XML 与变盘接口。

## 2. 字段语义

### 2.1 盘口 XML

XML 记录以 `<i>字段1,字段2,...</i>` 形式逐行给出，`_xml_records` 按此切分，字段不足的记录直接丢弃。

| 接口 | 字段顺序 |
| --- | --- |
| `yp101.xml` | `公司ID,竞彩场次ID,oddsId,主水,盘口,客水` |
| `dx101.xml` | `公司ID,竞彩场次ID,oddsId,大球水,盘口,小球水` |
| `op101.xml` | `公司ID,竞彩场次ID,oddsId,初主,初和,初客,终主,终和,终客` |

两条必须记住的约定：

1. **水位是香港水位**（`0.88` 这类），统一经 `_hong_kong_to_decimal` 换算为十进制赔率（`+1`）。
2. **盘口符号相反**。XML 里 `+0.25` 表示「主队让 0.25 球」，而页面 `parse_odds_page` 的
   `home_handicap` 用「负数 = 主队让球」。`parse_asian_xml` 因此输出 `home_handicap = -盘口`，
   两个来源的同一条记录落库后可直接比较。

`op101.xml` 的一段同时含初盘与终盘，`parse_h2h_xml` 因此每条记录展开为 `opening` + `current`
两个 stage（同一 `odds_id`，`sequence` 顺序为 `opening,current`）。`公司ID=0` 是跨机构平均行，
保留在结果里但不参与公司维度统计。

### 2.2 变盘历史

返回的是一段 HTML 片段，标题「近 5 次变化记录」，表体固定 4 列：`主队 | 盘口 | 客队 | 变化时间`。

- 表头行通过 `CHANGE_HEADER_CELLS` 过滤；
- 盘口是**长写**（`平手/半球`），与页面短写（`平/半`）不同，由 `LONG_LINE_PARTS` 映射，
  `受` 前缀表示客队让球（返回正值），同样遵循「负数 = 主队让球」；
- 变化时间是 `MM-DD HH:MM` 形式的展示串，可能带「初」后缀（如 `10-19 17:56初`），
  含「初」即初盘，落库为 `is_opening=true`；
- **该接口只回最近 5 次**，`sequence` 表示「本次抓取时在近 5 次中的位次（1 = 最新）」，
  新变盘出现时会整体向前滚动。

`cmd` 可取 `ypchange`（亚盘，代码当前只走这一路）、`opchange`（欧赔）、`dxqchange`（大小球），
三者实测均可用且结构一致。`oddsId` 只能从盘口 XML 拿到——页面 HTML 里没有这个 ID，
这也是变盘采集必须依赖 XML 的原因；注意 `op101.xml` 里 `公司ID=0` 的平均行 `oddsId` 也是 `0`，
用它请求会返回 `查询出错：正在中止线程。`，必须先剔除这类记录。

大小球变盘表的中列是纯数字盘口（如 `3.25`），不是亚盘长写，
`parse_change_table` 走 `long_asian_line` 时会得到 `handicap=None`——
若之后要启用 `dxqchange`，需要为大小球单独加一条解析分支。

## 3. 兜底触发条件

`capture()` 逐场处理 `mapped` 场次，页面链路抛出 `OSError` / `requests.RequestException` /
`ValueError`（含解析出 0 行时的 `no bookmaker quote rows`）即进入兜底：

1. 记入 `page_failures`；
2. 用该场次的 `nowscore_cp_match_id` 在三个 feed 里取 `xml_quotes(...)`；
3. 取到quote → 转 `to_outer_rows` 并计入 `fallback_matches`（场次标记为已覆盖）；
4. 取不到 → 复制 `page_failures[-1]` 到 `failures`，该场次状态为 `partial`。

注意兜底结果走的是同一套 `to_outer_rows`，因此**仍然受 `source_time_verified` 门禁**：
在线兜底 `source_time_verified=True`，离线（`--odds-html-dir`）恒为 `False`，
落库行会被标记 `reject_reason=offline_capture_time_unverified`，不会进入可研究集合。
`status` 只有在 `failures` 为空且 `captured_match_count == len(mapped)` 时才是 `complete`。

## 4. 采集与落库链路

变盘记录写入快照目录 `data/external/nowscore/snapshots/<sales_day>_<stamp>/price_changes.csv`，
字段在解析结果（`home_price_raw` / `handicap_raw` / `away_price_raw` / `changed_at_raw` /
`home_odds` / `away_odds` / `handicap` / `is_opening`）之上追加：

```
match_id, nowscore_match_id, cp_match_id, bookmaker_id, odds_id, sequence,
captured_at, raw_sha256, source_url, home_team, away_team, kickoff_at
```

末尾三个字段是为服务端匹配准备的（与 movement / alignment 通道一致：主客队名 + 北京时间开赛日期）。

同步链路：

```
run_controller_data_sync.py --stage market --sales-day <日期>
  → price_change_rows(day) 读该销售日最新快照的 price_changes.csv
  → POST /api/automation/sync-market { price_change_rows: [...] }
  → 匹配 fixtures 后 upsert 到 odds_price_changes
```

- 采集预算：`--change-bookmakers`（默认 `1,3,8`）与 `--max-change-requests`（默认 60），
  同时受 `max_duration_seconds` 约束；空字符串可关闭变盘采集。
- 落库去重键：`(sales_day, odds_id, change_key)`，`change_key` 由写入方按
  `odds_id|changed_at_raw|handicap_raw|home_price_raw|away_price_raw` 生成 sha1 前 24 位，
  因此重复抓取不会产生重复行。
- `odds_price_changes` 与 `fixture_market_intel` 同在
  `supabase/migrations/add_fixture_market_intel.sql`，需手动在 Supabase 执行一次。
- 未匹配到 fixtures 的变盘行只计数（`unmatched_price_changes`），不写库、不报错；
  当 `price_change_rows` 为空时路由不触碰该表，因此迁移执行前旧链路依然可用。

## 5. 审计字段

`capture()` 返回的 audit（落 `audit.json`）中与本次改造相关的字段：

| 字段 | 含义 |
| --- | --- |
| `cp_feed_row_counts` | 每个 feed 解析出的记录数（`{asian, totals, h2h}`） |
| `cp_feed_errors` | feed 抓取/解析失败明细 |
| `page_failures` | 赔率页失败明细（含 `nowscore_match_id`） |
| `fallback_match_count` | 靠 XML 兜底补齐的场次数 |
| `price_change_rows` | 变盘记录条数 |
| `price_change_match_count` | 有变盘记录的场次数 |
| `price_change_requests` | 实际发出的变盘请求数 |
| `change_failures` | 变盘请求失败明细 |

## 6. 实测记录（2026-10-21）

- `yp101.xml` / `dx101.xml` / `op101.xml` 均 HTTP 200，分别解析出 180 / 72 / 504 行
  （`op101` 的 252 条记录各展开为初盘 + 终盘两行）；
- `handle/odds.aspx` 三个 `cmd` 均 HTTP 200 且结构一致；
  `cmd=ypchange` 解析出真实变盘记录，其中一条
  `0.88 平手/半球 0.96 10-19 17:56初` → `handicap=-0.25`、`is_opening=true`；
- 长写盘口抽查：`平手/半球 → -0.25`、`受半球 → 0.5`、`三球/三球半 → -3.25`；
- 兜底路径用 mock 验证：页面失败 → XML 补齐 → `status=complete`、`fallback_match_count=1`；
  XML 无对应场次时保持 `partial` 并写入 `failures`。

## 7. 注意事项

- 只用普通 UA 与 `Cache-Control: no-cache`，**不绕过验证码、不做登录态模拟**；请求量有明确上限。
- 变盘接口在赛前可用，赛后不保证返回；`turn=1` 只拿最近 5 次，需要更长历史必须靠多次采集累积。
- 该数据当前仅用于研究性影子特征（`odds_price_changes` 是独立事件流表），
  未接入任何生产模型特征，与 `prematch_coverage.py` 的
  `blocked_until_timestamped_prematch_coverage_is_sufficient` 门禁无关。
