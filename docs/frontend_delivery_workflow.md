# 前端开发交付流程

这份文档用来让你“不会前端也能推进前端”，并且在多智能体协作时保证前端改动可验收、可回滚、不互相覆盖。

## 前端在本项目中的定位

前端工程在 `web/`，它同时承担：

- 页面展示（`/setup`、`/fixtures`、`/predictions`、`/chat` 等）
- 在线 API 层（Next.js route handlers）
- Supabase 读写

它不承担：

- 训练任务
- 大规模回测
- 正式自动化总控

## 交付的基本单位

前端开发不以“改了哪些文件”为验收，而以“一个可用能力”为验收。

推荐交付单位：

- 一个页面的可用版本
- 一个 API 接口的可用版本
- 一个模块级改动（例如统一布局、错误处理、鉴权）

每次交付尽量聚焦一个能力，避免同时改太多模块。

## 分工建议

### Trae Work

负责：

- 页面结构与交互设计
- 代码实现与联调
- 规范性封装（`src/lib/`）
- 提供验收方式与截图/说明

### 云端电脑智能体

适合：

- 写页面组件
- 改样式与布局
- 做接口联调与展示优化

### 本地 Codex

适合：

- 跑构建验证
- 处理需要本地凭据的环境配置
- 做最终合并前的检查

## 开发流程

### 1. 新建分支

```powershell
git checkout -b feature/web-<topic>
```

建议命名示例：

- `feature/web-predictions-ui`
- `feature/web-chat-polish`
- `fix/web-supabase-timeout`

### 2. 本地开发命令

在仓库根目录：

```powershell
.\scripts\project.ps1 web-lint
.\scripts\project.ps1 web-typecheck
.\scripts\project.ps1 web-build
```

如果你只是要起 dev server，在 `web/` 目录：

```powershell
npm install
npm run dev
```

## 验收标准

每个前端任务建议至少满足以下 4 项：

1. 页面可打开，不崩溃
2. 关键交互有错误提示
3. API 请求失败时能展示可理解的错误，而不是无响应
4. `web-build` 可通过

如果任务涉及 Supabase 或外部数据源，还建议：

- `/setup` 页面能明确提示环境变量是否齐全
- `/api/status` 能给出健康状态

## 与数据库联动的约束

前端页面不直接依赖本地 CSV 或 Python `artifacts/`。

页面展示的数据原则上来自 Supabase：

- 赛程：`fixtures`
- 赔率：`odds`
- 预测：`fixture_predictions`

如果 Python 研究链路产生了新字段，应该先：

1. 通过迁移更新 Supabase schema
2. 再更新 `web/src/lib/databaseTypes.ts`（如果有）
3. 再更新前端展示

不要先在前端写“假字段”硬接，这会造成协作混乱。

## 如何避免多智能体互相覆盖

建议用“页面归属”的方式划分任务：

- 一个页面同时只有一个主开发者
- 其他智能体只提交小 PR 或补丁

如果必须多人协作同一页面：

1. 先拆分 UI 模块为组件
2. 让不同智能体分别负责不同组件
3. 主开发者负责集成与最终验收

## PR 描述模板

前端 PR 描述建议包含：

- 本次改动影响的页面与路由
- 新增或变更的 API
- 依赖的环境变量
- 如何本地验证
- 是否包含数据库 schema 变更

## 常见问题

### 前端要展示 Python 训练结果，应该怎么做？

推荐：

1. Python 把结果写入 Supabase `fixture_predictions`
2. Web 读取并展示

不推荐：

- Web 直接读取 Python `artifacts/`

### 前端是否需要支持“自动化总控状态”？

建议支持，但展示的数据来源要明确：

- 如果是“线上状态”：写 Supabase 状态表或运行记录表
- 如果是“本地运行状态”：先通过脚本导出摘要，再决定是否上云

不要让前端直接去读本地机器上的状态文件。

## 推荐推进顺序

当前建议前端按这个顺序推进：

1. 统一布局与导航
2. `/predictions` 展示增强（筛选、联赛、时间、概率与赔率并排）
3. `/fixtures` 数据质量提示（缺赔率、缺队名映射）
4. `/chat` 与预测/赛程联动（引用 fixture id）
5. 视需要新增“自动化总控状态页”
