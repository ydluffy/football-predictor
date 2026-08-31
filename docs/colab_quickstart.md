# Colab 训练快速说明

这份文档的目标不是把 Colab 变成生产环境，而是让你能用最简单的方式，在 Google Colab 上拉取当前仓库、读取 Google Drive 数据、运行 `football-predictor/` 的训练命令。

## Colab 在本项目里的定位

Colab 适合：

- 临时训练和实验
- 跑研究型 notebook
- 做数据分析和回测
- 保存临时模型产物到 Google Drive

Colab 不适合：

- 作为正式自动化总控
- 作为代码真源
- 作为线上服务环境

## 你需要准备的东西

开始前需要有：

1. 一个可访问 GitHub 仓库的 Colab 环境
2. 一个 Google Drive 目录用于放训练数据
3. 需要训练的数据文件，例如 `real_matches_standardized.csv`

## 推荐目录约定

建议在 Google Drive 建这几个目录：

```text
MyDrive/
  ball-match-prediction-system/
    data/
    outputs/
```

建议把训练数据放在：

```text
MyDrive/ball-match-prediction-system/data/
```

## 最简单的 Colab 流程

### 1. 挂载 Google Drive

```python
from google.colab import drive
drive.mount('/content/drive')
```

### 2. 拉取 GitHub 仓库

如果仓库可直接访问：

```python
!git clone https://github.com/ydluffy/football-predictor.git
```

进入 Python 工程目录：

```python
%cd /content/football-predictor/football-predictor
```

注意：真正的 Python 工程在仓库里的 `football-predictor/` 子目录，不是在仓库根目录直接跑。

### 3. 安装依赖

```python
!python -m pip install -U pip
!pip install -r requirements.txt
!pip install -e .
```

## 数据放置方式

不要把训练数据推到 GitHub。代码放 GitHub，数据放 Google Drive。

示例：

```python
DATA_PATH = "/content/drive/MyDrive/ball-match-prediction-system/data/real_matches_standardized.csv"
```

## 最小训练命令

示例一：逻辑回归基线

```python
!python scripts/run_train.py --model-type logit --feature-version v1 --calibration none --cv false --data-path "$DATA_PATH"
```

示例二：LightGBM

```python
!python scripts/run_train.py --model-type lightgbm --feature-version v4 --calibration none --cv false --data-path "$DATA_PATH"
```

## 训练结果在哪里

训练结果默认会写入：

- `artifacts/models/`
- `artifacts/eval/`

这些文件都在 Colab 运行目录里。如果你想长期保留，训练完后复制到 Google Drive。

示例：

```python
!mkdir -p /content/drive/MyDrive/ball-match-prediction-system/outputs
!cp -r artifacts /content/drive/MyDrive/ball-match-prediction-system/outputs/
```

## 更推荐的保存方式

更稳的做法不是每次全量复制 `artifacts/`，而是只保存关键文件，例如：

- 模型文件
- `metrics.json`
- `model_compare.csv`
- 需要回看的评估报告

## 如果要同步最新代码

如果你已经 clone 过仓库，后续同步：

```python
%cd /content/football-predictor
!git pull --rebase
%cd /content/football-predictor/football-predictor
```

如果你要切换到某个任务分支：

```python
!git checkout chore/cloud-collab-setup
```

## 推荐的 Colab 使用方式

### 方式一：只训练，不改代码

这是最适合你当前阶段的方式：

1. 代码在本地或 GitHub 改好
2. Colab 只负责拉代码和跑训练
3. 输出存回 Drive

### 方式二：做 notebook 分析

如果你要做世界杯、赔率、联赛覆盖、回测可视化等分析，也可以在 Colab 用 notebook，但 notebook 结论最终应回写成仓库文档或脚本，不要只留在 Colab 页面里。

## 不建议这样用

以下方式不建议：

- 直接在 Colab 里长期改仓库代码
- 把 `artifacts/`、训练数据和大文件推回 GitHub
- 把 Colab 当成正式自动化环境
- 让 Colab 持有唯一版本的关键脚本

## 适合下一步做的事

等 GitHub 协作跑通后，最推荐的下一步是：

1. 建一个 Colab notebook 模板
2. 固定 Google Drive 数据目录
3. 用当前仓库的 `run_train.py` 跑一次真实训练
4. 把结果保存回 Drive
5. 再决定是否要把训练结果写回 Supabase 或做前端展示

## 当前阶段的建议

当前先完成 GitHub 和协作规范最重要。Colab 放在第二阶段推进最合适，因为：

- 仓库真源要先稳定
- 分支与文档要先明确
- 云端电脑和本地 Codex 的边界要先清楚

这样后面接入 Colab 才不会把代码、数据和产物混在一起。
