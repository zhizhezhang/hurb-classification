# 数据清洗与人工复核准备

在项目根目录运行（仅使用 Python 标准库，输入沿用任务 01 报告）：

```powershell
python scripts/prepare_data_cleaning.py --dataset "Chinese Medicine datasets" --audit "reports/data_audit"
```

默认输出到 `reports/data_cleaning/`。数据集路径和报告路径均可配置；`--output` 可改输出目录，但不能放在原始数据集内。脚本不重新解码、哈希或审计原图，不删除、移动、重命名或修改原始数据。

用浏览器直接打开 `reports/data_cleaning/review.html`。页面内嵌候选数据，图片通过相对路径从原数据集读取。保持 HTML 与原数据集的相对目录关系；移动 HTML 前需重新运行脚本并指定输出目录。逐对审核 pHash 候选，在单图复核栏处理低分辨率、极端宽高比及抽样中需关注的图片。页面可导出 JSON 或 CSV；JSON 可导入以继续审核。浏览器本地缓存仅作便利副本，应定期导出 JSON 保存审核记录。

方向键快捷操作：焦点不在搜索框、组下拉框或备注框时，`←` / `↑` 切上一组，`→` / `↓` 切下一组；在单图页切换上一张/下一张。更新页面后请刷新浏览器；同一文件地址下的本地审核记录会继续读取，建议刷新前先导出 JSON 备份。

`clean_manifest.csv` 只包含 SHA-256 去重后的有效代表文件；`excluded_images.csv` 记录自动排除的完全重复副本；`processing_log.csv` 对每张原图记录处理动作；`duplicate_groups.csv` 包含完全重复组与待复核的 pHash 连通组；`phash_pair_mapping.csv` 可追溯任务 01 的每一对候选。pHash 组只是导航，不能据此自动排除图片或作为未来划分数据集的同源分组。只有逐对人工确认的“同源重复”关系可作为后续处理依据。本任务不划分训练、验证和测试集。

## 应用人工复核导出

完成审核并导出 JSON 后，可选用同一时刻导出的 CSV 交叉校验：

```powershell
python scripts/apply_review_decisions.py --decisions "<path-to-review_decisions.json>" --review-csv "<path-to-review_decisions.csv>"
```

脚本生成 `reviewed_clean_manifest.csv`、`reviewed_excluded_images.csv`、`confirmed_source_groups.csv`、`pending_review_pairs.csv`、`review_application_log.csv` 和 `review_report.md`。它只应用明确的单图“排除异常样本”，并只把明确选择“同源重复”的图片对组成确认关系组；未选择或暂不确定的项继续保留。原始数据和基线清单保持不变。
