# ConvNeXt-Tiny 中药材分类训练工程

本工程的 `herb_classifier/preprocessing.py` 原样保存已验收的预处理实现，`herb_classifier/data.py` 提供训练适配器；固定数据划分仍位于上一级 `reports/data_split/`。训练入口只读取 `train.csv` 和 `val.csv`，不读取测试集。原始图像始终只读。

## 环境与命令

在仓库根目录，将内层工程可编辑安装到所选 Python 环境后，即可从仓库根目录、内层工程目录或现有 `backend/` 稳定导入同一个 `herb_classifier` 包。当前 `herb-classifier` Conda 环境可运行：

```powershell
python -m pip install -e '.\convnext-herb-classifier' --no-deps --no-build-isolation
```

这一步只安装本项目的可编辑包，不安装或升级 PyTorch、Torchvision、CUDA 依赖。

在 PyCharm 中将项目解释器设为已有的 `herb-classifier` Conda 环境，直接运行根目录的 `train.py`。终端中激活该环境后，从内层工程目录运行：

```powershell
python train.py
```

默认读取 `train.py` 顶部 `CONFIG_FILE` 指向的 YAML。在 PyCharm 中直接修改这一行即可选择配置；终端也可以运行 `python train.py configs/other.yaml` 或 `python train.py --config configs/other.yaml` 临时指定。相对路径始终以 `train.py` 所在目录为基准。运行前会打印实际使用的 YAML 路径；完整配置随后保存在新实验目录的 `train_config.yaml`。

单独冒烟测试可运行 `python scripts/smoke_test.py`。

冒烟测试默认使用配置中的 batch size 8，训练 2 个 batch、验证 2 个 batch，并在 `runs/smoke_test/` 保存增强对比图、测试专用 checkpoint 和资源记录。若显存不足，可显式使用 `--batch-size 4`；实际值会记录。Windows 多进程 DataLoader 可在 YAML 中设置 `num_workers`，入口均有 `if __name__ == '__main__'` 保护。

YAML 中的 `experiment_name` 设置实验名称，`runs_dir` 设置输出根目录。每次运行都会原子创建 `实验名_北京时间时间戳_序号` 目录，不覆盖旧实验。`epochs: 20` 是训练上限；完整验证集 Macro-F1 决定 `best.pt`，patience=5 提前停止。每轮指标及显存写入 `metrics.csv`。正常结束后自动重载最佳权重，使用完整验证集生成 `results.png`、原始和归一化混淆矩阵、`classification_report.csv` 与 `training_summary.md`；原有 `loss_curve.png` 和 `accuracy_curve.png` 继续输出。`last.pt` 还含优化器与 AMP 状态。`run_info.json` 记录 Python、PyTorch、Torchvision、CUDA 和 GPU 信息；`run_status.json` 仅在训练及报告都完成后标记为 `completed`。异常中断会尽量保留已写日志并标记失败。可用 `herb_classifier.model.load_checkpoint(path, device)` 独立加载。正式训练仅在 CUDA 可用时运行。

自动报告无需另行运行脚本。若需要从已有实验**重建一份隔离报告**，指定原实验和全新输出目录：

```powershell
python scripts/analyze_validation.py --run-dir runs/convnext_tiny_20261027_run01 --output-dir runs/report_check
```

已有依赖：PyTorch、Torchvision、Pillow、NumPy、PyYAML、Matplotlib。没有必要重装 PyTorch 或 Torchvision。CUDA 计算可能存在非确定性算子；随机种子已设置，但不强制完全确定性以避免明显降低训练性能。
