# 模型、数据与评估

## 数据集与固定划分

项目从 18 类、5,366 张原始图片开始进行数据治理。删除 53 张完全重复副本，并经人工复核排除 38 张异常图片，得到 **5,275 张有效图片**。固定划分为训练 **3,692**、验证 **795**、独立测试 **788** 张；同源组不跨子集。原始图片未纳入 Git，详见[审计](../reports/data_audit/report.md)、[人工复核](../reports/data_cleaning/review_report.md)与[划分报告](../reports/data_split/split_report.md)。类别映射见 `reports/data_split/class_to_idx.json`。

## 模型与训练

训练工程在 `convnext-herb-classifier/`，以 ImageNet 预训练的 ConvNeXt-Tiny 迁移学习。图片按 `reports/data_split/preprocess_config.json` 的配置预处理；训练入口、数据增强、优化器和学习率等具体参数以[训练工程说明](../convnext-herb-classifier/README.md)及归档的 `experiments/run02/train_config.yaml` 为准。训练只读取训练集与验证集，使用验证集 Macro-F1 选取最佳轮次。Run01 和 Run02 的真实过程见[实验日志](experiment-log.md)及 `experiments/`，本阶段没有重新训练。

| 已归档运行 | 最佳轮次 | 验证集 Accuracy | 验证集 Macro-F1 |
| --- | ---: | ---: | ---: |
| Run01 | 3 | 95.97% | 95.64% |
| Run02（部署选择） | 8 | 96.98% | 96.62% |

Run02 第 8 轮权重在独立测试集上的结果：**Accuracy 97.08%**、**Macro-Precision 97.11%**、**Macro-Recall 96.67%**、**Macro-F1 96.76%**；788 张中正确 765 张、错误 23 张。这些数值来自[最终测试归档](../experiments/final_evaluation/evaluation_summary.md)及[原始指标](../experiments/final_evaluation/test_metrics.json)，与上表验证集指标分开统计。

人参测试样本 35 张，正确 24 张，Recall 约 0.686；图片形态、背景和相近根片可能影响分类，详见最终评估中的定性观察。当前模型只覆盖上述 18 类，Top-1 概率是分类输出，不等于实物身份鉴定。

## 权重与推理

默认权重路径是仓库根目录 `models/convnext_tiny_best.pt`；`HERB_MODEL_PATH` 可指定绝对路径，或相对于仓库根目录的路径。启动时后端校验权重类别、预处理配置及最终评估归档的 SHA-256。模型在应用生命周期开始时加载；缺少权重或校验失败时服务无法完成启动。权重约 111 MB，被 Git 忽略，GitHub Release 附件尚未发布，下载地址待正式发布并校验后补充。已有权重的持有人可复制 Run02 第 8 轮 `best.pt` 到默认路径；仅克隆仓库无法运行图像识别。完整步骤见[部署文档](deployment.md)。
