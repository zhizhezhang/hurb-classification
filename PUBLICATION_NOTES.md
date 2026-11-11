# 独立公开发布副本说明

本目录由参赛开发分支 `competition/vibe-coding` 的已验收提交 `c7a80fa9d8aad0cc0d989a53aa8dca461f16e9eb` 使用 `git archive` 导出。导出时共有 207 个受 Git 管理的文件。此目录未复制原 `.git`，不包含原有 33 个提交的历史；独立公开仓库的首次提交记录的是发布快照，不代表此前没有 AI 协作开发。原始开发工作区和提交历史保持原样。

## 导出与脱敏范围

- 未导出原始训练图片、模型权重、虚拟环境、`node_modules`、运行时数据库、上传图片、缓存及密钥。`models/README.md` 仅说明未来模型附件的放置与校验方式。
- 在本公开副本中，将实验归档的 `experiments/final_evaluation/test_metrics.json`、`experiments/run02/run_info.json`，以及数据治理报告中的 4 份 JSON 路径字段改为仓库相对路径。指标、类别、划分和文件哈希记录未改；原始归档仍保留在参赛开发工作区。
- 将 `experiments/final_evaluation/evaluation_summary.md`、C4.1/C4.2/C4.6 报告、数据审计与清洗报告、`scripts/README_data_cleaning.md` 中的本机工作区或 Python 解释器路径改为相对路径、`python` 命令或明确占位符。仅在本副本做路径脱敏，原始报告未改。
- 数据审计、清洗与人工复核三份历史报告原有 17 个链接指向从未纳入 Git 的原始审计附件；公开副本将其标为“原始附件未随公开源码提供”，保留文件名、数值和结论。
- 后端测试中的 `D:\private` 是故意构造的错误路径，用于验证服务不泄露内部位置；保留测试原文。江西拙楷字体来源记录中的本地压缩包路径保留，以保存真实来源信息。`C:/Windows/Fonts` 是数据脚本引用的系统字体目录，不是个人账户路径。

## 素材与开发记录

用户在 C6.3 明确确认现有页面图片为本人原创或 AI 生成、可公开分发；包括药材插画、书本、卷轴、纸张和背景。既有[素材清单](docs/asset-manifest.md)记录了 27 张迁移图片的文件哈希，不单独证明创作来源。用户也已确认江西拙楷字体可使用并公开分发，本副本保留字体文件、CSS 引用及[原始来源记录](frontend/src/assets/fonts/JiangXiZhuoKai-SOURCE.md)。另一字体的 SIL OFL 文本随仓库保留。没有对页面视觉元素做修改。

真实联调报告与浏览器截图保留在 `reports/competition/`；[AI 开发迭代索引](docs/competition/ai-development-record.md)给出三组用户需求、问题修正与可核对实现。完整对话导出和 Codex 逐字回复未随仓库归档，索引不将它们冒充为已保存的原始记录。

## 发布前待办

本公开副本已为原创源码添加 MIT License 并初始化独立 Git 仓库。模型权重的单独许可声明尚未确定，第三方资源仍遵循各自适用的授权条件。GitHub Release 附件尚不存在，文档不含虚构下载链接；远程发布需另行确认。
