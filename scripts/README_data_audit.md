# 数据集分析脚本

在项目根目录运行（Windows PowerShell）：

```powershell
python -m pip install -r scripts/requirements_data_audit.txt
python scripts/audit_dataset.py --dataset "Chinese Medicine datasets"
```

`--dataset` 必填，可传绝对路径或相对当前工作目录的路径；默认输出到 `reports/data_audit/`。可通过 `--output` 修改输出目录，输出目录必须位于数据集之外。脚本仅读取原始文件。对每个文件使用 SHA-256；对可解码图片计算 64 位 DCT pHash。默认相似阈值是汉明距离 6，最多比较 2,000,000 个候选哈希对，最多导出 200,000 个 pHash 图片对。达到限制时会在 `summary.json` 和报告中标记结果未完成。运行 `python scripts/audit_dataset.py --help` 查看全部参数。

候选筛选使用 `阈值 + 1` 个互不重叠的哈希位段索引。汉明距离不超过阈值的两个哈希必有至少一段相同，因此在未触及比较上限时不会漏掉阈值内的哈希对。相同 pHash 的图片直接归组。pHash 只是视觉相似候选；跨类别候选需人工核对标签与采集来源。后续划分训练、验证、测试集前，应按确认的重复/近重复组进行分组，避免数据泄漏。

主要输出：`report.md`、`summary.json`、`images.csv`、`class_summary.csv`、`anomalies.csv`、`exact_duplicate_groups.csv`、`phash_similar_pairs.csv`、`cross_class_candidates.csv`、`class_counts.png`、`image_dimensions.png` 和 `sample_grids/` 下的各类抽样网格。CSV 使用 UTF-8 BOM，方便 Windows Excel 直接打开。
