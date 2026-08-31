# Supabase 初始化与迁移执行

这份文档用于把“数据库是否做好”变成一件可检查的事。你不需要懂数据库细节，只要按步骤做，就能确认 Supabase 是否真的建好了。

## 这份仓库里已经有什么

数据库迁移文件在：

- `supabase/migrations/`

目前已有迁移文件，涵盖：

- `fixtures`
- `odds`
- `fixture_predictions`
- `backtest_runs`
- `team_name_translations`

## Supabase 在本项目的定位

Supabase 用于线上业务数据与前端展示数据：

- Web 页面优先从 Supabase 读取
- Python 研究链路如果要给前端使用，应写入 Supabase

训练数据和 `artifacts/` 不放 Supabase。

## 初始化步骤（推荐）

### 1. 创建 Supabase 项目

在 Supabase 控制台创建一个新项目，记录：

- Project URL
- Service Role Key

注意：这些是敏感信息，不要提交到 GitHub。

### 2. 配置 Web 环境变量

在本地或 Vercel 环境变量中设置：

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

在本地可以先放到 `web/.env.local`（不要提交）。

### 3. 执行迁移

迁移的执行方式取决于你是否使用 Supabase CLI。

如果你已经装了 Supabase CLI，并且希望本地管理迁移，建议：

1. 先把仓库 `supabase/` 目录与 Supabase 项目关联
2. 然后把 `supabase/migrations/` 里的 SQL 逐个应用到远程项目

如果你暂时不想折腾 CLI，也可以先用 Supabase SQL Editor 手动执行迁移文件里的 SQL（按时间顺序）。

关键原则：

1. 只执行 `supabase/migrations/` 中的内容
2. 保持迁移顺序一致
3. 不在控制台里随手改表结构而不回写迁移文件

### 4. 验证表是否创建成功

验证标准：

1. Supabase 控制台中能看到上述表
2. Web 的 `/api/status` 能返回“数据库可用”

建议你用 Web 的状态接口做验证，因为它代表真实运行路径。

## 多智能体协作时的数据库变更规则

数据库结构属于高影响区域，需要更严格的协作规则：

1. 同一时间只允许一个任务分支改迁移
2. 迁移文件通过 PR 合并
3. PR 必须说明是否需要对 Supabase 远程执行新迁移

不要让多个智能体在不同分支同时新增迁移文件，否则很容易产生顺序冲突。

## 常见坑

### 1. 前端能跑，但查询为空

这通常不是 bug，而是数据尚未写入：

- `fixtures` 没有导入
- `odds` 没有导入
- `fixture_predictions` 没有产出

先确认数据导入链路，而不是直接改页面。

### 2. 用错 Key

Web 的服务端接口通常需要 `Service Role Key` 才能写表。
不要把这个 key 暴露到浏览器端。

### 3. 在 Supabase 控制台手改结构

如果你在控制台里手动新增列，但没有写迁移文件，后续任何环境重建都会丢结构，协作也会混乱。

原则：结构变更必须通过迁移文件体现。

## 推荐下一步

等 GitHub 协作流程跑通后，建议再做两件事：

1. 补一份“数据库表字段说明”（对齐前端展示）
2. 决定是否要新增：
   - 模型版本表
   - 自动化运行记录表
   - 数据源抓取状态表

这些在你准备做更完整的线上状态面板时会用到。
