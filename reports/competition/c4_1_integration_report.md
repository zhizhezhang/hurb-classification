# C4.1 端到端联调与浏览器验收

日期：2026-11-07。分支：`competition/vibe-coding`，基线 `1fdadb1`。保留 C1～C3 未提交成果；未修改 main、未提交 Git、未配置或调用真实 DeepSeek。

## 1. 环境与启动

- Windows；后端使用现有 `python`，前端使用现有 Node.js 与 Vite 7.3.7。
- 目标 worktree 未包含忽略的模型权重、原始测试图片及 `frontend/node_modules`。测试期间只读借用主工作区的现有权重、图片和依赖；测试用临时链接与图片副本已清理。
- 临时本地 FastAPI 测试入口以 `python -m reports.competition.c4_1_mock_server` 启动，监听 `127.0.0.1:8765`。原定 8000 端口已被其他进程占用。该临时脚本现已删除。
- 测试入口将 `backend.services.ai_service` 的 HTTP 客户端替换为 `httpx.MockTransport`，使用仅本地有效的占位 Key；识别成功场景仍调用真实 ConvNeXt。测试数据库和上传目录位于系统临时目录。
- Vue 以 `HERB_API_PROXY_TARGET=http://127.0.0.1:8765; npm run dev` 启动在 `127.0.0.1:5173`。浏览器使用 ChatGPT 内置 Chromium 浏览器。服务均已停止。

## 2. 后端 HTTP 联调

实际请求均为 `POST /api/ai/chat`，由本地服务经真实 HTTP 处理。DeepSeek 响应仅由 MockTransport 生成。

| 场景 | HTTP | grounding_status | answer_origin | 来源 | 结果 |
| --- | ---: | --- | --- | ---: | --- |
| 黄芪外貌，无 ID | 200 | grounded | model_with_retrieved_context | 1 | `huangqi.appearance`、S1 |
| 人参与黄芪外貌对比 | 200 | grounded | model_with_retrieved_context | 2 | 两药各一条、S1/S2 |
| 当归名字典故 | 200 | grounded | model_with_retrieved_context | 1 | `danggui.allusion` |
| 未收录三七 | 200 | insufficient | local_guardrail | 0 | 明确资料不足 |
| 普通文化问题，无 ID | 200 | ungrounded_legacy | model_general | 0 | 不虚构来源 |
| 伪造 S99 | 200 | insufficient | local_guardrail | 0 | 不返回假来源 |
| 模拟超时 | 504 | — | — | — | `DeepSeek request timed out` |
| 模拟上游 500 | 502 | — | — | — | `DeepSeek upstream request failed` |
| 模拟空答 | 502 | — | — | — | `DeepSeek returned an invalid response` |
| 有效 `herb_id=huangqi` | 200 | grounded | model_with_retrieved_context | 1 | 回显 ID，旧字段 `success/data.answer/data.herb_id/data.model` 保留 |

失败响应无成功数据或来源，错误详情未含 Key、上游原文或堆栈。另由后端自动化测试覆盖 404 非法 ID、422 空白/超长消息、401/402/429 等上游错误映射。

## 3. 浏览器链路

- **A 成功识别：**上传真实测试图片 `人参/04 (1).jpg`，ConvNeXt 返回人参 99.89%，图鉴简介正常。问“它的外貌如何？”返回人参外貌、S1 来源和“不能确认实物身份”的说明，证明当前 ID 被用于问答上下文。
- **B 双药对比：**问“人参和黄芪在外貌方面有什么区别？”，回答含 S1/S2；对应来源按人参、黄芪各显示一次。来源没有重复、遮挡或横向溢出。
- **C 资料不足：**问“三七的外貌是什么样？”，显示资料不足说明，当前回复下无“参考依据”区域；随后仍可继续发送消息。
- **D 低置信度：**临时测试入口按文件名注入 0.5999 结果，页面显示原有“识别失败”，没有识别结果或图鉴简介。此时“这张图是什么药材？”明确拒绝确认；主动点名黄芪仍得到黄芪资料与 S1。无上下文代词问法的边界问题见第 6 节。
- **E 切换图片：**先上传延迟 2 秒返回的人参测试副本，立即上传另一张真实图片 `人参/04 (101).jpg`；最终显示黄芪 94.23%。延迟的人参响应没有覆盖黄芪结果，随后问“它的外貌如何？”得到黄芪资料和来源。切换期间清空旧预测与药材上下文。
- 模拟上游超时时，聊天区显示原有“发送失败，请稍后重试。”，输入框仍可继续使用。

## 4. 视觉与截图

实测浏览器视口 922×871、1366×768、1920×1080。聊天面板在各桌面视口保持 700px 宽、底部居中；两种设定桌面视口下无横向溢出，消息滚动到最新回复。输入框、发送按钮、识别结果区域和国风背景未作改动。Markdown 回答保留原渲染方式；自动化测试覆盖原生 HTML 转义。

下列均为实际浏览器截图：

- [单条来源](c4_1_screenshots/single.jpg)
- [双药来源](c4_1_screenshots/compare.jpg)
- [资料不足](c4_1_screenshots/insufficient.jpg)
- [低置信度与主动点名查询](c4_1_screenshots/low_confidence.jpg)
- [切换图片后的黄芪上下文](c4_1_screenshots/switched.jpg)
- [1366×768 桌面视口](c4_1_screenshots/desktop_1366.jpg)
- [1920×1080 桌面视口](c4_1_screenshots/desktop_1920.jpg)

## 5. 自动化回归

- 完整后端：`python -c "...unittest.defaultTestLoader.discover('backend/tests')..."`，将预测测试的数据集根指向主工作区只读原图，并临时链接同一权重；**62 项通过**。最小修复后再次运行仍为 **62 项通过**。
- 完整前端：在 `frontend/` 运行 `node --test tests/*.test.js`，**20 项通过**。
- 生产构建：在 `frontend/` 运行 `npm run build`，**通过**，129 个模块转换。
- `git diff --check`：**通过**。
- 唯一测试环境提示为现有 Starlette `httpx` 弃用警告，无测试失败。8000 端口占用、Edge 扩展未启用文件 URL 上传权限，因此联调改用 8765 端口和内置 Chromium 浏览器；这不影响应用功能结论。

## 6. 发现、复现与最小修复

**P2，已修复：**低置信度识别后，由于前端正确地不传 `herb_id`，无明确药名的“它的外貌如何？”被后端当作普通文化问答交给模型；Mock 返回了与提问不相关的一般回答。复现：上传 0.5999 测试图片 → 打开聊天 → 发送该问题。仅在 `backend/services/knowledge_retrieval.py` 的无实体分支补充代词指代检查，返回原有“没有可核实的药材上下文”说明；在 `backend/tests/test_ai.py` 增加检索与 API 不调用上游的断言。未改动图鉴、模型、阈值、前端视觉或接口格式。修复后的完整后端测试通过；该浏览器场景的修复结果由 Mock 自动化测试确认，未在浏览器中重新截图。

**2026-11-09 浏览器补验：**使用原始测试图 `无花果/无花果 (44).png` 经真实 ConvNeXt 识别，页面进入低置信度“识别失败”。发送“它的外貌如何？”后，回复为“没有可核实的药材上下文，不能确认图片中的药材身份。”；当前回复无药材形态描述、无“参考依据”区域。测试进程显式清空 `DEEPSEEK_API_KEY`，此问题由本地规则回答，未调用真实 DeepSeek。[实际页面截图](c4_1_screenshots/low_confidence_pronoun_verified.jpg)。上段“未在浏览器中重新截图”描述的是 C4.1 当日状态，本补验已补齐该证据。

**P3，保留的交互局限：**切换图片后，聊天窗口仍保留此前图片的历史问答。新请求已使用当前药材或无 ID，但旧消息没有图片上下文标签，用户可能把历史回复误认为当前图片的资料。本阶段未改变聊天历史行为或页面设计。

**P3，能力边界：**Mock 验证了前后端协议与可视呈现，不能证明真实 DeepSeek 对引用格式的遵循率或所有自然语言事实的准确性。库外药材识别仍限现有 C2 规则。

## 7. C4.2 准备情况

本阶段 **0 次真实 DeepSeek 请求**，未配置真实 Key、未产生付费调用。离线接口、浏览器链路和回归测试已通过，具备进入受控 C4.2 联调的技术条件；真实模型格式遵循率和上述 P3 交互局限仍需在后续阶段评估。进入 C4.2 前须由用户明确授权实际调用，并以安全方式提供服务端 Key；本报告未记录任何真实凭据。
