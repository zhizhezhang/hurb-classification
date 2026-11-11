# FastAPI 后端

后端在 `backend/main.py` 中创建 FastAPI 应用。启动时加载本地 ConvNeXt-Tiny 权重、18 条图鉴资料、问答 Skill、模型分析归档，并初始化 SQLite 识别历史。完整安装与配置见[部署文档](../docs/deployment.md)，架构见[系统架构](../docs/architecture.md)。

从仓库根目录启动：

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

默认模型路径为 `models/convnext_tiny_best.pt`，可通过 `HERB_MODEL_PATH` 指定其他路径；相对路径按仓库根目录解析。权重未纳入 Git，缺失或校验失败会阻止服务启动。`HERB_DEVICE` 可选 `auto`、`cpu` 或 `cuda`。默认历史数据库与上传目录是 `backend/runtime/history.db` 和 `backend/runtime/uploads/`，可用 `HERB_HISTORY_DB_PATH`、`HERB_UPLOADS_DIR` 覆盖。运行时数据均不提交到仓库。

## API

| 路径 | 功能 |
| --- | --- |
| `GET /api/health` | 运行状态与模型加载情况 |
| `POST /api/predict` | JPEG/PNG 图片推理，`multipart/form-data` 字段 `file`；返回 Top-3 并保存有效识别记录 |
| `GET /api/herbs`、`GET /api/herbs/{herb_id}` | 图鉴列表与详情 |
| `GET /api/history`、`GET /api/history/{record_id}`、`GET /api/history/{record_id}/image`、`DELETE /api/history/{record_id}` | 识别历史 |
| `GET /api/model/info`、`GET /api/model/metrics`、`GET /api/model/charts/{name}` | 已归档模型分析 |
| `POST /api/ai/chat` | 本草知识库、DeepSeek AI 和旧客户端兼容问答 |

图片限制为 10 MiB、2000 万像素，且必须能解码为 JPEG/PNG。后端图鉴来自 `backend/data/herbs.json`；`references` 不自动作为聊天答案的句子级证据。历史使用 SQLite，模型分析来自 `experiments/run02/` 与 `experiments/final_evaluation/`。

聊天请求包含 `message`（1–2000 字符）、可选 `herb_id`、可选 `mode`（`knowledge` 或 `deepseek`）。知识库模式只读取内置资料并返回实际来源，不调用模型；DeepSeek 模式用一次普通文本模型调用，回答不附带本地来源；不传 `mode` 时保留历史兼容路径。有效识别上下文只传入药材 ID，DeepSeek 只获得预测中文名称的文字提示，不接收图片。具体状态与来源语义见[AI 助手文档](../docs/ai-assistant.md)。

`DEEPSEEK_API_KEY` 只在后端环境配置；缺少时需要调用 DeepSeek 的请求返回 HTTP 503，其他接口照常可用。上游超时和异常有对应 HTTP 错误码，不向客户端暴露密钥或内部堆栈。

在已准备本地权重与测试图片的环境中运行完整后端测试：

```powershell
python -m unittest discover -s backend/tests -v
```

测试中的 DeepSeek 响应使用 Mock，不产生真实 API 调用。
