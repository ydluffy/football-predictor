# 云端电脑协作与切换

这份文档解决两个问题：

1. 云端电脑如何接入同一个项目并参与协作
2. 当你在“本地电脑 ↔ 云端电脑”之间切换开发时，如何避免数据丢失、互相覆盖、环境漂移

## 基本原则

1. 代码以 GitHub 为真源，云端电脑只通过 Git 获取代码
2. 生产性自动化总控当前只在本地运行，云端电脑不承担正式总控
3. 云端电脑参与协作时必须在独立分支工作
4. 任意智能体修改前必须先 `pull`，修改后必须 `push` 并通过 PR 合并

## 云端电脑首次接入

### 1. Clone 仓库

在云端电脑打开终端，执行：

```powershell
git clone https://github.com/ydluffy/football-predictor.git
cd football-predictor
```

如果仓库是私有的，需要先在云端电脑完成 GitHub 登录，再 clone。

### 2. 切换到任务分支

不要直接在 `main` 上改：

```powershell
git checkout -b agent/coze/<topic>
```

如果你要接手某个已有分支：

```powershell
git fetch
git checkout <branch-name>
```

### 3. 安装依赖与运行

云端电脑一般只需要做开发和验证：

- 前端开发：在 `web/` 目录安装依赖并运行
- Python 开发：在 `football-predictor/` 安装依赖并跑测试

具体命令以根目录 `README.md` 和 `scripts/project.ps1` 为准。

## 本地与云端切换时的“安全动作”

每次切换环境前后，都建议按这个顺序做。

### 从本地切到云端

1. 本地确认工作区干净或已提交

```powershell
git status --short
```

2. 本地把当前工作推到远程分支（不要推 `main`）

```powershell
git push
```

3. 云端电脑拉取最新远程分支

```powershell
git pull --rebase
```

### 从云端切回本地

1. 云端电脑确认已提交并推送

```powershell
git status --short
git push
```

2. 本地拉取远程分支

```powershell
git pull --rebase
```

## 多智能体并行协作的冲突控制

当你同时使用本地 Codex、云端电脑上的多个智能体时，最容易出问题的是“同时改同一块逻辑”。

建议按模块划分任务：

- `web/`：页面、路由、API handler、展示层
- `supabase/migrations/`：数据库迁移
- `football-predictor/`：训练、研究、自动化、策略、脚本
- `docs/`：协作规范与说明

并行协作时，尽量做到：

1. 一个任务只改一个模块
2. 一个模块同时只由一个智能体做“主改动”
3. 其他智能体只做审查或补丁

## 需要“单写入者”的高风险区域

以下区域建议同一时间只有一个智能体写入：

1. `supabase/migrations/`
2. 自动化总控相关的核心逻辑（例如 `football-predictor/src/strategy/`）
3. 任何会影响真实台账、真实投注的脚本
4. 与密钥、鉴权、生产环境相关的配置文件

如果需要多人协作同一高风险区域，必须先约定“谁是主改动者”，其他人通过 PR 评论给建议。

## 云端电脑不要做的事

云端电脑不建议做以下事情：

- 承担正式自动化总控（尤其是真实台账、正式投注）
- 长时间持有唯一运行中的状态文件
- 存放唯一版本的训练数据
- 直接保管生产密钥

云端电脑最适合做“代码与文档协作”，而不是“生产运行”。

## 云端数据与密钥管理

### 密钥原则

1. 密钥不写入仓库
2. 使用 `.env` 文件或平台的环境变量配置
3. 云端电脑不要长期保存生产密钥

### 推荐做法

- Web 相关密钥：交给 Vercel 环境变量管理
- Supabase 管理密钥：只在必要时临时使用
- Python 研究密钥：本地 `.env` 或云端临时注入

## 云端与本地的产物同步

任何属于“生成产物”的内容不通过 Git 同步：

- `football-predictor/artifacts/`
- `data/raw/`、`data/manual/`、`data/processed/`
- `web/node_modules/`、`web/.next/`

这些内容要么保留在运行环境本地，要么保存到外部存储（例如 Google Drive、对象存储）。

如果产物需要被前端使用，应该写入 Supabase 表，而不是让前端读取本地 `artifacts/`。

## 遇到冲突时怎么处理

当 `git pull --rebase` 或合并出现冲突：

1. 停下来，不要强推、不做硬重置
2. 把冲突文件列表和冲突片段发给 Trae Work 或你本人
3. 决定用哪个分支为准，再继续合并

如果你不确定，宁可先开一个新分支保存现场：

```powershell
git checkout -b backup/<topic>
git add .
git commit -m "chore: backup before conflict resolution"
git push -u origin backup/<topic>
```

## 推荐下一步

等 GitHub 推送稳定后，你可以让云端电脑上的智能体按这份文档 clone 仓库，然后优先接手：

- 前端页面与接口联调
- 文档维护
- 数据获取层对比与迁移
- Colab 训练环境准备
