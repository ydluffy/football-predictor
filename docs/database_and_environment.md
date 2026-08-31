# 数据库与环境说明

这份文档定义项目当前的数据库职责、环境边界和部署关系，避免前端、Python 研究链路、云端电脑、Colab 各自使用不同的数据真源。

## 当前数据库定位

项目当前的线上结构化数据层以 Supabase 为主。

已存在的迁移包括：

- `supabase/migrations/init_p0.sql`
- `supabase/migrations/add_odds_table.sql`
- `supabase/migrations/add_fixture_predictions_and_backtests.sql`
- `supabase/migrations/add_team_name_translations.sql`

当前核心表：

- `fixtures`
- `odds`
- `fixture_predictions`
- `backtest_runs`
- `team_name_translations`

## 推荐的数据职责划分

### Supabase

Supabase 作为在线业务数据真源，负责：

- 页面展示所需的赛程、赔率、预测结果
- 在线查询接口
- 回测摘要结果
- 翻译和映射类持久化表

### 本地 `football-predictor/`

本地 Python 工程负责：

- 原始数据导入
- 训练、研究、回测
- 生成模型产物
- 影子证据、报告、台账、审计文件

这些内容多数保留在本地，不直接入库。

### Colab / 云端训练环境

Colab 和云端训练环境负责临时训练与实验，不直接作为业务数据真源。实验成功后，结果应通过人工确认或明确脚本写回 Supabase，而不是把 Colab 目录当成生产来源。

## Web 与 Python 的关系

### Web 层

`web/` 负责：

- 页面
- 在线 API
- Supabase 查询与写入
- 与用户直接交互的展示层

### Python 层

`football-predictor/` 负责：

- 更复杂的数据导入
- 训练评估
- 自动化总控
- 世界杯、体彩、影子策略等研究逻辑

建议原则：

1. Python 产出模型概率或预测结果
2. 将可用于前端展示的结果写入 Supabase
3. Web 从 Supabase 读取，不直接依赖本地 `artifacts/`

## 当前最重要的环境变量

### Web / Vercel

用于 `web/`：

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `FOOTBALL_DATA_API_KEY`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `API_FOOTBALL_KEY`

### Python / `football-predictor`

常见变量见 `football-predictor/.env.example`，包括：

- `MODEL_PATH`
- `CODING_PLAN_API_KEY`
- `CODING_PLAN_BASE_URL`
- `CODING_PLAN_MODEL`
- `OPENROUTER_API_KEY`
- `FOOTBALL_DATA_TOKEN`
- `THE_ODDS_API_KEY`
- `API_FOOTBALL_KEY`
- `SPORTMONKS_API_TOKEN`
- `SERPAPI_API_KEY`
- `P0_DB_PATH`

## 环境边界

### 本地环境

本地环境目前承担正式自动化和正式研究工作。以下内容优先保留在本地：

- 自动化总控运行
- 正式投注与台账
- 审计文件
- 本地敏感凭据

### 云端电脑

云端电脑用于开发、实验和协作，不承担正式生产职责。可以使用它来：

- clone 仓库
- 做前端开发
- 做非生产性脚本开发
- 对比其他项目的数据获取层

### Vercel

Vercel 只负责部署 `web/`。不要把训练、回测、自动化总控直接塞进 Vercel。

### Colab

Colab 只作为训练和分析工作台，不负责线上服务和正式调度。

## 数据流推荐

建议的数据流如下：

1. 数据源进入 `football-predictor/`
2. 经过标准化、验证、训练、评估
3. 需要在线展示的结果写入 Supabase
4. `web/` 从 Supabase 读取展示

不要让前端直接读取：

- 本地 CSV
- 本地 `artifacts/`
- 研究中间文件

## 当前数据库建设还需要补的部分

虽然迁移已经存在，但后续还建议继续完善：

1. 明确每张表的 owner 和用途
2. 补初始化步骤文档
3. 补部署环境变量清单
4. 视业务推进补：
   - 模型版本表
   - 自动化运行记录表
   - 世界杯专用预测表
   - 任务编排与运行状态表

## 建议执行顺序

如果接下来继续推进数据库建设，建议按这个顺序：

1. 先确认现有 Supabase 项目和表是否已经真实创建
2. 运行并核对迁移
3. 验证 `web` 的 `/api/status`、`/api/fixtures`、`/api/predictions`
4. 再决定是否补模型版本表和自动化状态表

## 与协作规范的关系

任何涉及数据库变更的任务，都应：

1. 新建独立分支
2. 修改迁移文件而不是直接口头约定
3. 说明是否影响 `web`
4. 说明是否影响 `football-predictor`
5. 在 PR 中写明变更目的和回滚思路

数据库结构变更属于高影响改动，不应由多个智能体在不同分支上同时随意修改。
