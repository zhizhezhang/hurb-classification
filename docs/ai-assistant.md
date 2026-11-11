# 双模式本草助手

当前界面在识别页的聊天区域手动切换“本草知识库”和“DeepSeek AI”。两种模式均调用 `POST /api/ai/chat`，请求格式为 `{ "message": "...", "mode": "knowledge" | "deepseek", "herb_id": "可选药材 ID" }`。`message` 最多 2000 字符；不传 `mode` 的旧客户端沿用兼容路径。当前页面显式发送模式，不使用旧路径作为双模式路由。

## 本草知识库

`knowledge` 模式调用 `backend/services/knowledge_retrieval.py`，直接使用 `backend/services/herb_service.py` 已加载的 18 条图鉴资料。可按明确药材名称检索外貌、传统功效、典故等字段，支持两药比较；明确名称优先于识别上下文。有效 `herb_id` 可以用于“它的外貌如何”“有什么功效”等省略药名的问题。没有可识别药材或资料不足时，本地简洁回复并可提示切换模式，不自动调用 DeepSeek。明确的助手身份与能力问题由本地固定回答处理。

资料型回答由后端直接组织，返回本次实际使用的 `sources`，来源名称为“灵枝本草内置药材资料”。传统功效按传统本草资料呈现，不代表现代医学已证实的治疗作用。库外药材识别能力有限，明确的“三七”场景会拦截；不能把未匹配的所有问句都可靠判定为库外药材。

## DeepSeek AI

`deepseek` 模式由 `backend/api/ai.py` 调用 `backend/services/ai_service.py` 的普通文本路径，经现有 HTTP 客户端发送**一次** Chat Completions 请求。该模式不运行知识字段检索、自动意图分类、结构化 JSON 输出或引用校验。模型返回的文本或 Markdown 原样作为回答，经前端已有安全 Markdown 渲染机制显示；`sources=[]`，系统不把模型自行提到的来源标为已验证证据。必要的密钥、个人用药安全边界和上游错误处理仍由后端执行。

若请求附带有效 `herb_id`，后端仅从图鉴映射中文药材名称，作为 ConvNeXt **预测类别的文字上下文**传给模型。聊天接口不接收图片；明确点名其他药材的问题应以用户文字为准。普通聊天或创作也不强制关联当前识别结果。

## 识别上下文与响应

识别页只有在 Top-1 概率达到 0.60、状态为 success 且预测类别可映射为图鉴 ID 时，才把 ID 传入聊天组件。换图即清空旧 ID，过期异步结果不覆盖新状态。前端在发送瞬间固定所选模式和当前 ID，避免切换后把响应归错模式。

响应保留 `success`、`data.answer`、`data.herb_id`、`data.model`，并带 `grounding_status`、`answer_origin`、`sources`。`grounded` 表示知识库使用了本地图鉴资料；`insufficient` 表示本地资料不足或安全边界；`ungrounded_legacy` 表示回答没有经知识库事实校验。`answer_origin=local_knowledge` 是本地资料回答，`local_guardrail` 是本地规则回答，`model_general` 是 DeepSeek 普通文本回答。旧兼容路径还可能返回 `model_with_retrieved_context`，其历史实现包含结构化输出与引用校验；该机制不是当前两个显式模式的工作方式。引用编号合法本身不能证明自然语言断言准确。

示例：

```json
{"message":"黄芪的外貌如何？","mode":"knowledge"}
```

成功时 `data.sources` 包含本次使用的药材、字段与 S 编号；DeepSeek 模式则不返回内置来源。接口契约以 `backend/schemas/ai.py` 为准。

历史 C1 方案与 C4 联调过程见[设计记录](competition/knowledge-enhanced-ai-design.md)及[参赛测试报告](../reports/competition/)。这些记录描述各阶段演变，不能代替当前双模式实现说明。
