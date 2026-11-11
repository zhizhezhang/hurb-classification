# 07.2 本地部署与环境核验记录

核验日期：2026-10-30（Asia/Shanghai）。仓库基线：`main`，`8d09261 docs: update project README and setup instructions`。本文记录**当前机器的已验证状态**，不是跨机器可直接安装的依赖锁文件；没有导出完整 `pip freeze` 或 Conda 环境，也没有重新安装或升级依赖。

## 1. 运行环境

| 检查项 | 状态 | 实测值或依据 |
| --- | --- | --- |
| Conda / Python | PASS | 环境 `herb-classifier`；Python 3.11.18。使用该环境的解释器直接导入项目和依赖。 |
| PyTorch / Torchvision | PASS | `torch 2.13.0+cu126`；`torchvision 0.28.0+cu126`。 |
| CUDA / GPU | PASS | PyTorch 构建 CUDA 12.6，`torch.cuda.is_available()` 为 `True`；NVIDIA GeForce RTX 4060 Laptop GPU，驱动 581.80，显存 8188 MiB（`nvidia-smi`）。这里的 12.6 是 PyTorch 报告的 CUDA 构建版本。 |
| 关键 Python 依赖 | PASS | FastAPI 0.162.0、Uvicorn 0.54.0、python-multipart 0.0.32、httpx 0.28.1、Pillow 12.3.0、NumPy 2.4.6、PyYAML 6.0.3、Matplotlib 3.11.2、setuptools 84.0.0，均可导入或由包元数据查得。 |
| 项目 Python 包 | PASS | `convnext-herb-classifier 0.1.0` 为可编辑安装；`pip show` 的 Editable project location 指向仓库内 `convnext-herb-classifier/`；`herb_classifier`、`data`、`model`、`preprocessing` 模块均解析到该目录下唯一的 `herb_classifier/`，没有解析到仓库根目录的重复包。 |
| Node.js / npm | PASS | Node.js v24.11.0；npm 11.6.1。 |
| 前端锁文件 | PASS | `frontend/package.json` 与 `frontend/package-lock.json` 的直接依赖声明一致，锁文件版本 3，现有 `node_modules/` 存在。锁文件版本：Vue 3.5.44、Vue Router 4.6.4、Vite 7.3.7、`@vitejs/plugin-vue` 6.0.10、Axios 1.21.0、markdown-it 15.0.3。安装命令为在 `frontend/` 执行 `npm ci`；本轮未重新安装，命令仅作静态核验。 |

项目 Python 包的 `pyproject.toml` 要求 Python ≥3.10、setuptools ≥61。`convnext-herb-classifier/requirements.txt` 只列 NumPy、Pillow、PyYAML、Matplotlib；`backend/requirements.txt` 固定 FastAPI、Uvicorn、python-multipart、httpx。PyTorch、Torchvision 及 CUDA 安装方案未由完整锁文件固定；当前运行环境可用，不代表已验证从空环境跨机器复现。

## 2. 模型权重与加载

| 检查项 | 状态 | 结果 |
| --- | --- | --- |
| 部署权重 | PASS | `models/convnext_tiny_best.pt` 存在，111,392,415 字节。 |
| Run02 最佳权重 | PASS | `convnext-herb-classifier/runs/convnext_tiny_lr3e5_20261028_113820_001/best.pt` 存在，111,392,415 字节；该运行目录被 Git 忽略。 |
| SHA-256 一致性 | PASS | 两份文件均为 `202072243d01e7e47a4e008e0e6480d5446a2124f48f8512cca1ea3b379e814f`；与 `experiments/final_evaluation/test_metrics.json` 记录的部署检查点哈希一致。只读计算，未修改权重。 |
| 后端默认路径 | PASS | `Settings.from_env()` 在当前 shell 解析为仓库根目录的 `models/convnext_tiny_best.pt`。未设置 `HERB_MODEL_PATH` 时使用该路径；新启动进程已完成应用 startup，随后因 8001 端口冲突退出。 |
| 模型结构 | PASS | 现有 8001 服务的 `/api/health` 返回 `model_loaded=true`、`model_name=convnext_tiny`、18 类、`device=cuda:0`；`/api/model/info` 返回 Run02 第 8 轮版本、224 输入、27,833,970 参数及 ImageNet 预训练来源。启动代码核对检查点类别映射、预处理配置与最终评估权重哈希。 |

现有 8001 进程没有提供“当前权重绝对路径”查询接口，因此无法从其 HTTP 响应直接读取进程环境中的 `HERB_MODEL_PATH`；上述默认路径由本轮新进程解析和启动加载过程核验。

## 3. 按 README 运行核验

| 检查项 | 状态 | 结果 |
| --- | --- | --- |
| 后端独立启动命令 | BLOCKED | 在仓库根目录执行 `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001`，进程报告 `Application startup complete`，随后绑定端口报 `[Errno 10048]` 并正常关闭：8001 已由现有 Python 进程监听。本轮未终止该进程，也未改端口或项目配置。 |
| 复用现有后端 | PASS | 现有进程使用 `herb-classifier` 环境解释器；`GET http://127.0.0.1:8001/api/health` 为 200，返回 `status=ok`、模型已加载、18 类、CUDA 设备；`GET /docs` 为 200 且返回 Swagger UI；`GET /api/model/info` 为 200。 |
| 前端独立启动命令 | NOT RUN | 5173 已由现有 Node 进程监听；按任务要求复用现有 Vite 服务，未再启动第二个严格占用 5173 的实例。`vite.config.js` 的开发端口为 5173 且 `strictPort=true`。 |
| 复用现有前端与代理 | PASS | `http://127.0.0.1:5173/` 和四条页面路径均返回 200；`http://127.0.0.1:5173/api/health` 返回与 8001 相同的健康响应。`vite.config.js` 明确读取 `HERB_API_PROXY_TARGET`，README 中的变量名正确。现有服务的启动命令和进程环境无法从 HTTP 响应直接读取，但代理的实际响应已验证。 |
| 页面路由与刷新 | PASS | 浏览器直达并刷新 `/recognition`、`/atlas`、`/history`、`/analysis`；主内容出现，图鉴完成加载后显示人参，分析页显示 Run02 模型概览与最终测试四指标。 |
| 静态素材 | PASS | 浏览器加载的 Logo、两侧装饰、图鉴古书、18 张药材图片、历史卷轴、Accuracy 曲线及归一化混淆矩阵均有非零自然宽度；抽查素材 HTTP 响应为 200 `image/png`。 |
| 浏览器控制台 | PASS | 四页访问、刷新及图鉴完成加载后，当前浏览器会话未记录 error 级日志；这是本轮路径范围的检查。 |
| 预测与真实 DeepSeek | NOT RUN | 本轮未上传图片进行完整推理，也未发送 DeepSeek 请求。健康检查、模型概览和页面读取均无需付费调用。 |

README 中的 `Set-Location` 路径、PowerShell 调用运算符 `&`、`backend.main:app` 模块路径、8001 端口、5173 前端端口及代理变量已按当前结构核对；后端命令实际执行至端口绑定阶段。`pip install -r`、可编辑安装和 `npm ci` 均**仅静态核验**，没有重新执行。`pip show` 与模块 `__file__` 已证实当前可编辑安装结果。未配置 DeepSeek 密钥时其他核心接口仍可使用，是根据路由及 `AISettings` 代码隔离关系核对；本轮未为此重启一个无密钥的独立服务。

## 4. 交付依赖分类

| 类型 | 项目 |
| --- | --- |
| Git 已包含 | 前后端源码与依赖声明、`frontend/package-lock.json`、`backend/data/herbs.json`、问答 Skill、`frontend/public/assets/` 所用素材、`reports/data_split/` 的类别映射及预处理配置、`experiments/run02/` 与 `experiments/final_evaluation/` 的指标和图表。 |
| Git 忽略但运行必需 | `models/convnext_tiny_best.pt`；可运行的 Python 环境及其 PyTorch/Torchvision/CUDA 兼容依赖；前端安装后的 `node_modules/`。原始 Run02 `runs/.../best.pt` 是本地归档副本，正常部署无需同时复制它。 |
| 运行时自动生成 | 默认 `backend/runtime/history.db`、`backend/runtime/uploads/`；`HistoryStore.initialize()` 创建目录与 `recognition_history` 表。历史数据库和用户上传图片不是交付必需文件。 |
| 可选配置 | `DEEPSEEK_API_KEY`（仅知识问答需要，真实值不得提交）、`DEEPSEEK_MODEL`（默认 `deepseek-flash`）、`HERB_MODEL_PATH`、`HERB_DEVICE`、`HERB_HISTORY_DB_PATH`、`HERB_UPLOADS_DIR`、开发代理 `HERB_API_PROXY_TARGET`。 |

运行限制：当时主要验证 Windows 本地环境；Python 依赖未完整锁定，需自行准备兼容的 PyTorch/Torchvision 与 CUDA 环境。模型权重未纳入 Git，也没有公开下载地址。`npm ci` 和 Python 安装命令本轮未重新执行，不能把本轮记录当成空环境安装成功证明。素材清单中两张未迁移原图现存位置仍待确认，它们不属于本轮已验证页面的加载依赖。

## 5. 06.6 遗留项

以下保留原[06.6 报告](../reports/system_integration_test_06_6.md)的事实，本轮没有改写报告。06.6.1 第 11 节是 D-01/D-02 定向复测的较新状态。

| 项目 | 状态 | 当前记录 |
| --- | --- | --- |
| D-01 输入框文案、D-02 窄屏矩阵 | PASS | 06.6.1 已定向修复并复测；D-02 报告仍写“待用户视觉验收”。本轮只做部署核验，未重新测试这两项视觉细节。 |
| D-03 智能识别断连提示 | FAIL | 06.6.1 在断连代理下显示易误解的“识别失败，请重新选择图片”；本阶段未改业务代码，未重复该故障注入测试。 |
| 指定 pytest 入口 | BLOCKED | 06.6 记录 Conda 环境缺少 pytest；本轮未安装或重新运行 pytest。后端现有 56 项 `unittest` 在 06.6 中通过，本轮未重复运行。 |
| 真实 DeepSeek 调用 | NOT RUN | 06.6 与本轮均未执行付费上游请求。 |
| Hover Tooltip、动画帧率/主观流畅度、槐花素材来源 | NOT RUN | 原报告仍待核实；本轮未据页面能打开而改为通过。 |

报告第 1–10 节保留首轮失败与未执行记录，第 11 节补充 D-01/D-02 修复和部分复测；这属于按时间记录的状态变化。建议未来若复测 D-03 或补齐其他遗留项，另增定向记录，并保留原始测试事实。
