# 中国体彩数据获取 API 策略

## 当前结论

中国体彩/竞彩网可以看到公开网页数据，但当前没有确认可稳定调用的正式开放 API。项目已验证：

- `webapi.sporttery.cn/gateway/jc/football/getMatchInfoV1.qry` 直连会被 WAF 拦截。
- 加常见浏览器请求头后，接口返回 `E0001 请求错误`，说明还缺少真实前端参数、会话条件或服务端校验。
- `getMatchResultV1.qry` 类接口在当前环境返回 `禁止访问`。

因此不建议把体彩隐藏接口直接包装成生产 API。这样做看起来自动化，但稳定性、合规性和可复盘性都不够。

## 可行路线

### 1. 本地权威数据 API

已实现。

接口：

```text
GET /world-cup/sporttery/handicap-markets?date=YYYY-MM-DD
```

数据来源：

```text
data/manual/sporttery_handicap_markets_YYYY-MM-DD.csv
```

如果当天 CSV 不存在，接口会返回根据世界杯 fixtures 生成的待填列表；如果 CSV 存在，接口会解析真实盘口并返回：

- `home_handicap_raw`：原始填写值，例如 `主队让1球`
- `home_handicap`：模型内部数值，负数表示主队让球，正数表示主队受让
- `is_filled`：是否已填写真实盘口
- `source` / `updated_at` / `notes`：来源和审计字段

### 2. 浏览器导出/半自动采集

可作为下一阶段开发，但建议只做“辅助导出”，不要做绕过 WAF 的爬虫。

可接受方式：

- 用户在本机浏览器正常打开中国体彩/竞彩网页面。
- 使用浏览器复制表格、保存 HTML、截图 OCR 或人工导出 CSV。
- 项目只负责解析本地导出的文件，并记录来源。

不建议方式：

- 批量请求隐藏接口。
- 模拟验证码、绕过 WAF、复用非授权 Cookie。
- 对官网高频轮询。

### 3. 第三方数据交叉校验

雷速、公开赔率页面或新闻转载可以用于校验赛程、球队名、盘口方向是否异常，但“真实体彩盘口”字段应优先来自体彩官方页面、App 截图或官方公告。

## 推荐工作流

1. 生成当天待填表：

```powershell
.\.venv\Scripts\python.exe scripts\build_sporttery_handicap_template.py --as-of-date 2026-06-25
```

2. 从体彩官方页面/App 核对让球盘，填入：

```text
data/manual/sporttery_handicap_markets_2026-06-25.csv
```

3. 查看本地 API：

```text
GET /world-cup/sporttery/handicap-markets?date=2026-06-25
```

4. 跑日报：

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_daily_pipeline.py `
  --as-of-date 2026-06-25 `
  --sporttery-markets data/manual/sporttery_handicap_markets_2026-06-25.csv `
  --dry-run false
```

## 本地编辑页

已实现一个轻量页面：

```text
GET /world-cup/sporttery/editor
```

启动 API 后打开该页面，可以：

- 选择日期并加载当天世界杯比赛
- 填写盘口阶段，例如 `opening`、`live`、`closing`、`latest`
- 填写采集时间；留空时系统自动记录当前时间
- 填写 `竞彩编号`
- 填写 `让球盘`
- 填写来源、更新时间、备注
- 保存到 `data/manual/sporttery_handicap_markets_YYYY-MM-DD.csv`

保存接口会校验让球盘格式，支持：

- `主队让1球`
- `主队受让1球`
- `平手盘`
- `-1`
- `+1`
- `0`

如果填写 `看好主队` 这类无法解析的内容，接口会拒绝保存，避免污染日报输入。

每次保存会同时写两份数据：

- 最新盘口文件：`data/manual/sporttery_handicap_markets_YYYY-MM-DD.csv`
- 历史盘口文件：`data/manual/sporttery_handicap_market_history.csv`

日报默认读取最新盘口文件；历史盘口文件用于后续分析盘口变化，比如从初盘到临场盘是否升盘、降盘，以及模型在不同盘口阶段的命中率。

## 后续可开发

- 本地 HTML 表格解析器：读取用户保存的体彩页面 HTML，自动抽取场次、主客队、让球。
- 截图 OCR 辅助填表：对体彩 App 截图做文字识别，再由人工确认。
- 数据质量门禁：日报运行前检查 `filled_count / count`，低于阈值则提示盘口未补齐。
- 前端编辑页：已完成基础版，可继续增加批量粘贴和 OCR 校验。
- 盘口变化分析：已具备历史数据落库基础，下一步可以计算初盘/临场盘变化幅度和方向。
- 赛后复盘分组：已支持按 `handicap_line_source` 和 `handicap_depth_bucket` 分析命中率，用来观察体彩真实盘与模型估盘、浅盘与深盘的表现差异。
- 盘口变化特征：已支持从 `sporttery_handicap_market_history.csv` 生成 `sporttery_handicap_line_movement_features.csv`，字段包括初盘、最新盘、变化方向、变化幅度、盘口加深/变浅。每日流水线会自动生成并传入复盘。
