# 实验日志

本日志依据数据治理报告、原始训练目录的 `train_config.yaml`、`metrics.csv`、训练总结，以及最终评估目录的 `test_metrics.json`、`classification_report.csv` 核对。`experiments/` 中的文件是原始实验文件的副本；权重和原始数据集仍只保存在本地。

## 数据治理与固定划分

1. [数据审计](../reports/data_audit/report.md)：检查原始 18 类、5,366 张图片；均可解码。发现 53 组 SHA-256 完全重复图片，并导出 366 对不同 SHA-256 的 pHash 相似候选，供后续复核。
2. [清洗准备](../reports/data_cleaning/report.md)：先排除 53 张完全重复副本，得到 5,313 张有效候选；pHash 相似性仅作复核线索，不自动删图。
3. [人工复核结果](../reports/data_cleaning/review_report.md)：明确排除 38 张异常图片，最终有效清单为 5,275 张；累计排除 91 张。360 对候选被人工确认为同源，形成 295 个确认关系组。对应的 [同源组 CSV](../reports/data_cleaning/confirmed_source_groups.csv) 是 `scripts/split_dataset.py` 默认读取的 `--groups` 输入，记录组内相对路径，不包含原始图片。
4. [固定划分与验证](../reports/data_split/split_report.md)：随机种子 42；按类别及已确认同源组约束划分，训练 3,692 张、验证 795 张、测试 788 张。独立验证确认划分互斥、覆盖有效样本、每部分均含 18 类，且确认同源组不跨子集。

## 模型训练与最终测试

| 阶段 | 学习率 | 最佳轮次 | 最佳验证 Accuracy | 最佳验证 Macro-F1 |
|---|---:|---:|---:|---:|
| [Run01](../experiments/run01/) | `1e-4` | 3 | 95.97% (`0.959748`) | `0.9564` (`0.956360`) |
| [Run02](../experiments/run02/) | `3e-5` | 8 | 96.98% (`0.969811`) | `0.9662` (`0.966238`) |

两轮都按完整验证集 Macro-F1 选取最佳轮次。最终选择 **Run02 第 8 轮 `best.pt`**；其原始位置是 `convnext-herb-classifier/runs/convnext_tiny_lr3e5_20261028_113820_001/best.pt`。最终测试报告记录的权重 SHA-256 为 `202072243d01e7e47a4e008e0e6480d5446a2124f48f8512cca1ea3b379e814f`。此权重文件未纳入 Git。

固定测试集共 **788 张、18 类**，正确 765 张、错误 23 张。最终 **Accuracy 97.08%** (`0.970812`)，**Macro-F1 0.9676**。详见 [最终评估归档](../experiments/final_evaluation/evaluation_summary.md) 与 [指标原始数据](../experiments/final_evaluation/test_metrics.json)。

已知局限性：**人参**测试集 35 张中识别正确 24 张，Recall 为 **0.686** (`24/35 = 0.685714`)；它是本次测试中需要重点关注的类别。该结论来自 [分类报告](../experiments/final_evaluation/classification_report.csv)。

归档只复制已有配置、指标、曲线和报告，没有重新训练或重新评估。原始运行目录及最终评估目录仍留在原位置。
