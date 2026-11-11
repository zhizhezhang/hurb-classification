# AI 协作开发迭代索引

本索引依据本次开发会话中可核对的用户需求片段、现存代码、真实测试报告和截图整理。引号中的内容为用户原话片段，并非完整 Prompt 逐字稿；完整对话及 Codex 逐字回复未随本仓库归档。以下“实现结果”是对仓库证据的归纳，不冒充 Codex 原始回复。开发日期和测试数字以链接报告为准。

## 迭代一：未收录药材与运行版本

- 用户发现的问题：“三七的外貌是什么样？”曾在浏览器中得到完整描述，要求未收录药材返回资料不足、零来源，且不能借用当前 `herb_id`。
- 后续人工排查确认此前浏览器连接的是旧运行服务；用户要求将参赛前后端放到独立端口，并通过 OpenAPI、代理与真实页面核对版本。
- 可核对的结果：当前知识检索对明确的“三七”场景执行本地拦截；[C4.2 实际页面截图](../../reports/competition/c4_2_screenshots/competition_5174_unknown_herb.jpg)和[测试计划](../../reports/competition/c4_2_real_deepseek_test_plan.md)记录了阶段性验收。对应实现见 `backend/services/knowledge_retrieval.py` 与 `backend/api/ai.py`。

## 迭代二：从自动路由调整为手动双模式

- 用户要求：“本草知识库 | DeepSeek AI”；选择知识库时不调用大模型，选择 DeepSeek 时直接显示模型文本，不用 S 编号校验普通聊天。
- 这项修改针对自动意图判断和严格证据校验影响普通交流的问题。后续人工测试又发现图像识别成功后两个模式没有正确获得当前药材上下文。
- 可核对的结果：`backend/api/ai.py` 根据显式 `mode` 走本地检索或一次 DeepSeek 普通文本调用；`frontend/src/components/recognition/DeepSeekChat.vue` 保留切换后的聊天记录。上下文修复的测试与浏览器结果见[C4.6 报告](../../reports/competition/c4_6_context_report.md)。

## 迭代三：识别上下文与本地身份回答

- 用户报告：识别完成后询问“有什么功效？”和“识别结果有什么功效？”仍得到资料不足或要求再次给出药材名称；又要求明确询问“你是谁”时，知识库给出固定助手介绍。
- 用户明确要求低置信度和换图后不沿用旧药材，DeepSeek 模式只接收 ConvNeXt 预测类别的文字上下文，并保留两种模式独立运行。知识库自我介绍随后通过人工测试。
- 可核对的结果：`frontend/src/views/RecognitionView.vue` 只在成功识别且能映射图鉴 ID 时传入上下文；知识库身份回答在 `backend/services/knowledge_retrieval.py` 本地生成。[C4.6 联调报告](../../reports/competition/c4_6_context_report.md)及 `backend/tests/test_ai.py`、`frontend/tests/knowledgeChat.test.js` 提供测试证据。

以上索引保留了真实问题、需求调整和证据入口；缺少完整原始 Prompt 及 Codex 回复的地方明确标记为资料不足。独立公开 Git 历史从发布快照开始，原始开发历史仍保留在独立工作区。
