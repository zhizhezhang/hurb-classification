# C4.6 识别上下文与双模式助手联调报告

## 环境与根因

- 工作区：`.`，分支：`competition/vibe-coding`。
- 修复前用参赛版 FastAPI 的 HTTP 接口复现：携带 `herb_id=dongchongxiacao` 询问“有什么功效？”和“识别结果有什么功效？”，均返回 `insufficient`、`sources=[]`。当时知识库的本地问句过滤未接受这两种省略药材名称的表达。
- 修复前 DeepSeek 模式的 HTTP 请求虽可携带合法 `herb_id`，服务端却只把 Skill 和原问题发给模型；模型消息没有预测药材名称。
- 前端原先仅从药材详情对象取 `herb.id`。预测类别已经映射到图鉴 ID、但详情请求失败时，聊天仍拿不到该 ID。

## 修复

- `backend/services/knowledge_retrieval.py`：仅在知识库模式接受“有什么功效”“识别结果有什么功效”“它的外貌如何”等当前药材指代问题；明确药材名称仍优先。没有有效上下文时提示先识别或提供名称。
- `backend/api/ai.py`、`backend/services/ai_service.py`：DeepSeek 模式验证并通过现有图鉴 ID 映射获取预测中文名，将其作为文字上下文放入系统消息，原始用户消息保持不变。普通文本回复仍经原有单次 HTTP 传输返回，`sources=[]`；不读取知识字段或执行引用校验。
- `frontend/src/views/RecognitionView.vue`：保留已映射的 ID，只有识别成功才传给聊天；换图立即清空，过期异步结果继续受 `selectionVersion` 检查。详情加载失败不会抹掉已经有效的类别映射。识别阈值仍为 0.60。
- `backend/tests/test_ai.py`、`frontend/tests/knowledgeChat.test.js`：补充 HTTP 路由、模型请求内容、前端请求体与上下文状态回归测试。

## 浏览器 Mock 联调

- 使用参赛版独立端口：前端 `127.0.0.1:5176`，后端 `127.0.0.1:8004`。建议的 5174/8002 在启动时拒绝绑定，因此改用空闲端口；没有终止其他进程。
- 前端 Vite 代理指向本次后端。OpenAPI 有可选 `mode`，前端提供双模式控件，经代理获取 18 条药材目录。
- 后端 DeepSeek URL 在测试进程内改为 `mock.invalid`，`httpx.MockTransport` 拦截请求，使用仅供 Mock 的虚拟密钥；没有连接真实 DeepSeek。
- 上传现有测试图片“九层塔 (100).png”，ConvNeXt 实际识别为九层塔，置信度 99.97%。知识库提问“有什么功效？”后显示九层塔 `traditional_effects` 和一条“灵枝本草内置药材资料”来源。切换 DeepSeek 模式再问同一句，Mock 回复显示已收到当前 ConvNeXt 预测类别“九层塔”，且没有知识库来源区域。
- 实际页面截图：[recognition_context_dual_mode.png](c4_6_screenshots/recognition_context_dual_mode.png)。临时服务在截图后已停止。

## 自动化结果

| 命令 | 结果 |
| --- | --- |
| `python -c "... unittest.defaultTestLoader.discover('backend/tests') ..."` | 78 项通过；使用已有模型的临时硬链接及主工作区测试图片，结束后移除硬链接 |
| `node --test frontend/tests/*.test.js` | 23 项通过 |
| `npm run build`（frontend） | 通过，Vite 129 个模块完成构建 |
| `git diff --check` | 通过 |

后端测试覆盖当前 ID 查功效与外貌、显式黄芪优先、无上下文提示、DeepSeek 单次请求的文字上下文、无图鉴检索和引用校验。前端测试检查实际构造的 `POST /api/ai/chat` 请求体，以及低置信度、换图清空和过期识别结果的现有门控。识别、图鉴和历史测试包含在完整后端与前端回归中。

## 限制

- DeepSeek 的真实生成质量未验证；本阶段仅用 Mock 确认收到预测类别，未发起付费 API 请求。
- 图片原始像素未发送给聊天模型；上下文是 ConvNeXt 的预测类别。图鉴名称无法成功映射时，不传递 `herb_id`。
- 工作区原有未提交成果保持原状；本阶段未执行 Git commit。
