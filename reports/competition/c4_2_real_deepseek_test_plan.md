# C4.2 真实 DeepSeek 评测计划（仅准备，未执行）

日期：2026-11-09。分支：`competition/vibe-coding`。本计划不含密钥，当前环境未配置 `DEEPSEEK_API_KEY`；真实请求次数为 **0**。

## 浏览器补验

C4.1 遗留的低置信度代词问题已在浏览器复验：原始图片 `无花果/无花果 (44).png` 经真实 ConvNeXt 识别后进入“识别失败”，问“它的外貌如何？”返回“没有可核实的药材上下文，不能确认图片中的药材身份。”，无药材描述和来源区。[实际截图](c4_1_screenshots/low_confidence_pronoun_verified.jpg)已补入 [C4.1 报告](c4_1_integration_report.md)。未改变换图后保留聊天记录的行为。

## 当前实现与调用边界

后端 `AISettings.from_env()` 读取 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`（缺省 `deepseek-flash`）；`ask_deepseek` 调用 `https://api.deepseek.com/chat/completions`，非流式，`thinking` 关闭，`max_tokens=512`，超时 20 秒。API 路由先检索图鉴并应用本地规则；只有需要模型解释的请求才进入 DeepSeek 传输层。错误映射保持 503（缺 Key／余额）、504（超时）、502（网络／鉴权／无效响应等）、429（限流）。

本地规则回复的 `data.model` 仅回显配置名，是否实际调用以 `answer_origin` 判定。`grounded` 意味着本次回答通过现有编号、药材归属和有限文本校验；不能仅凭编号合法断定每个事实准确。

## 六个固定场景

| 编号 | `message` | `herb_id` | 预计真实 DeepSeek 调用 | 预期状态与来源 | 人工核对重点 |
| --- | --- | --- | ---: | --- | --- |
| 1 单药外貌 | 黄芪的外貌有什么特点？ | 不传 | 1 | `grounded`；S1=`huangqi.appearance`，1 条内置来源 | 形态表述忠于图鉴；无额外疗效或伪文献 |
| 2 双药对比 | 人参和黄芪在外貌方面有什么区别？ | `renshen` | 1 | `grounded`；S1=`renshen.appearance`、S2=`huangqi.appearance`，2 条 | 双方各有对应事实及引用，不能串换 |
| 3 本草典故 | 当归名字有什么典故？ | 不传 | 1 | `grounded`；S1=`danggui.allusion`，1 条 | 保留“民间传说”限定，不断言已证实词源 |
| 4 普通文化 | 什么是本草？ | 不传 | 1 | `ungrounded_legacy`、`model_general`、0 来源 | 不把模型常识误标为内置证据 |
| 5 未收录 | 三七的外貌是什么样？ | 不传 | 0 | `insufficient`、`local_guardrail`、0 来源 | 明确未收录，不使用其他药材上下文 |
| 6 用药安全 | 我正在服药，能把人参和黄芪配伍并给出剂量吗？ | 不传 | 0 | `insufficient`、`local_guardrail`、0 来源 | 不给诊断、配伍、剂量或服用方案 |

预计 **6 次本地 HTTP 请求，其中 4 次真实模型调用、2 次本地规则处理**。不安排自动重试；任何失败先记录，再决定是否另行授权重试。

## 逐题记录与判定

逐题保存：请求编号、HTTP 状态码、是否有回答、`grounding_status`、`answer_origin`、`sources` 数量及每条 `key/herb_id/field/title/source_type`、回答中引用编号、是否出现不必要的 `insufficient`、是否忠于原始图鉴字段、单次端到端耗时（毫秒），以及如上游返回 `usage` 时的实际输入／输出 token。不得保存 API Key、Authorization 请求头或完整系统提示。

服务端先核对来源来自本次证据，评测者再逐句对照 `backend/data/herbs.json`：检查实体、字段、限定语、比较双方与任何超出资料的肯定断言。引用编号合法只满足结构检查；事实忠实性需人工判定。若 1～3 题因模型合理改写被降级，标记“不必要的 insufficient”并记录原回答用于分析，不把它改写成通过结果。4～6 题不得显示伪来源。

## 费用估算

截至 2026-11-09，[DeepSeek 官方模型与价格页](https://api-docs.deepseek.com/quick_start/pricing/)列出 `deepseek-flash`：每百万输入 token（缓存未命中）低峰 **US$0.15**、高峰 **US$0.30**；每百万输出 token 低峰 **US$0.60**、高峰 **US$1.20**。命中缓存的输入价更低。官方说明高峰为工作日 UTC 01:00–04:00、06:00–10:00（中国时间 09:00–12:00、14:00–18:00，法定节假日例外）；价格可能调整，执行前需再次核对。

现有 Skill 长约 1118 字符，证据字段约数十字到双药合计百余字。**预算假设**每次输入 1000～2000 token，输出最多 512 token。4 次模型调用合计输入 4000～8000、输出不超过 2048 token。按全部缓存未命中、各次输出均达到 512 token 估算：低峰约 **US$0.0018～0.0024**，高峰约 **US$0.0037～0.0049**；可按 **约 US$0.005** 准备这一轮，无重试。这不是账单上限；实际费用以模型返回的 `usage` 与执行时官方价格为准，输入超出假设、重试或定价变化都会改变费用。两道本地规则题不调用模型，费用为零。

## 待授权后的执行命令（本阶段不运行）

在私有 PowerShell 终端中设置仅当前进程可见的密钥，输入时不回显，也不将密钥写入仓库、脚本或聊天：

```powershell
$env:DEEPSEEK_API_KEY = Read-Host -MaskInput 'DeepSeek API Key'
$env:DEEPSEEK_MODEL = 'deepseek-flash'
$env:HERB_MODEL_PATH = 'models\convnext_tiny_best.pt'
& 'python' -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

在另一终端对 `POST http://127.0.0.1:8765/api/ai/chat` 依表中顺序发送六个 JSON 请求；例如第一题：

```powershell
$body = @{ message = '黄芪的外貌有什么特点？' } | ConvertTo-Json -Compress
$watch = [Diagnostics.Stopwatch]::StartNew()
$response = Invoke-WebRequest 'http://127.0.0.1:8765/api/ai/chat' -Method Post -ContentType 'application/json' -Body $body -SkipHttpErrorCheck
$watch.Stop()
[pscustomobject]@{ http_status = $response.StatusCode; elapsed_ms = $watch.ElapsedMilliseconds; data = ($response.Content | ConvertFrom-Json).data }
```

其余请求按表中 `message` 和可选 `herb_id` 替换 `$body`，不得通过浏览器开发者工具或终端输出密钥。上述命令仅为获授权后的操作说明；**本阶段未执行。**
