# 任务 02.2：同源约束划分与 ConvNeXt-Tiny 数据加载

在项目根目录、已安装相互兼容的 PyTorch/Torchvision 环境中运行。当前机器现有的 `Machine-Learning` Conda 环境已包含所需依赖；也可参考 `scripts/requirements_data_split.txt` 配置其他环境。以下命令只读取数据集和清洗结果：

```powershell
conda activate Machine-Learning
python -m pip install -e .\convnext-herb-classifier --no-deps --no-build-isolation
python -m scripts.split_dataset --dataset "Chinese Medicine datasets"
python -m scripts.validate_split --dataset "Chinese Medicine datasets"
```

输入默认读取 `reports/data_cleaning/reviewed_clean_manifest.csv`、`reviewed_excluded_images.csv` 和 `confirmed_source_groups.csv`。可通过 `--manifest`、`--excluded`、`--groups`、`--output` 配置路径；随机种子默认为 42。输出在 `reports/data_split/`。脚本按类别分别计算约 70/15/15 的整数目标，先分配完整的多图片同源组，再用独立样本填充余量。若目标比例与分组约束冲突，保留组完整并报告实际比例。不会移动、复制或改写原始图片。

数据模块位于 `convnext-herb-classifier/herb_classifier/`，其中 `preprocessing.py` 保存原有预处理实现，`data.py` 公开 `HerbImageDataset`、`create_dataloaders`、`get_train_transform`、`get_eval_transform`、`load_class_to_idx`。从仓库根目录运行划分脚本前，需在当前 Python 环境可编辑安装内层工程；详见[训练工程说明](../convnext-herb-classifier/README.md)。示例：

```python
from herb_classifier.data import create_dataloaders, load_class_to_idx

loaders = create_dataloaders(
    dataset_root="Chinese Medicine datasets",
    split_dir="reports/data_split",
    batch_size=16,
    num_workers=0,  # Windows 推荐从 0 开始
    seed=42,
)
images, labels = next(iter(loaders["train"]))
assert images.shape == (16, 3, 224, 224)
class_to_idx = load_class_to_idx("reports/data_split/class_to_idx.json")
```

训练集采用轻度随机裁剪、水平翻转与亮度/对比度/饱和度扰动；验证与测试使用 `ConvNeXt_Tiny_Weights.IMAGENET1K_V1.transforms()` 的确定性流程：短边缩放到 236、中心裁剪到 224、转换张量并使用 ImageNet 均值 `[0.485, 0.456, 0.406]` 和标准差 `[0.229, 0.224, 0.225]` 归一化。数据集读取时执行 EXIF 方向校正和 RGB 转换。推理服务应复用同一 `class_to_idx.json` 及 `get_eval_transform()`。

固定种子保证划分结果可复现。训练增强每次迭代仍会产生新的随机视图；`create_dataloaders` 会为采样器和工作进程设置种子。Windows 上使用多工作进程时，应从受 `if __name__ == "__main__":` 保护的入口调用。
