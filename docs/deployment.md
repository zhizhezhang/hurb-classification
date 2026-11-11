# 本地运行与部署说明

本文给出从仓库根目录运行开发服务的步骤。已验证环境记录见[本机核验归档](environment-verified.md)；Python、PyTorch 和 CUDA 依赖没有完整锁定，以下安装命令没有在全新机器上端到端验证。项目尚未验证 Docker、Linux 或一键生产部署。

## 1. 依赖

Python 项目声明 **Python ≥3.10**。先准备相互兼容的 PyTorch、Torchvision 和所需 CPU/CUDA 运行环境；再从仓库根目录安装项目依赖。前端使用 Node.js、npm，锁文件是 `frontend/package-lock.json`。

```powershell
python -m pip install -r .\convnext-herb-classifier\requirements.txt
python -m pip install -r .\backend\requirements.txt
python -m pip install -e .\convnext-herb-classifier --no-deps --no-build-isolation
Set-Location .\frontend
npm ci
Set-Location ..
```

可编辑安装需要环境已有 setuptools ≥61。安装时应选用已配置 PyTorch/Torchvision 的解释器；这些清单没有固定二者版本或 CUDA 组合。

## 2. 权重和配置

从[模型 Release](https://github.com/zhizhezhang/hurb-classification/releases/tag/model-run02-epoch8-f1f2c67)下载 [Run02 第 8 轮权重](https://github.com/zhizhezhang/hurb-classification/releases/download/model-run02-epoch8-f1f2c67/convnext_tiny_best.pt)，保存为仓库根目录的 `models/convnext_tiny_best.pt`。文件大小为 111,392,415 字节，SHA256 为 `202072243d01e7e47a4e008e0e6480d5446a2124f48f8512cca1ea3b379e814f`。也可设置 `HERB_MODEL_PATH` 为该文件的绝对路径或仓库根目录相对路径。权重不在 Git 历史中；缺失或不匹配会在 FastAPI 启动时失败。

Windows PowerShell（在仓库根目录执行）：

```powershell
$modelUrl = 'https://github.com/zhizhezhang/hurb-classification/releases/download/model-run02-epoch8-f1f2c67/convnext_tiny_best.pt'
$modelPath = 'models/convnext_tiny_best.pt'
Invoke-WebRequest -Uri $modelUrl -OutFile $modelPath
$expected = '202072243d01e7e47a4e008e0e6480d5446a2124f48f8512cca1ea3b379e814f'
$actual = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw '模型文件 SHA256 不匹配' }
```

Linux（在仓库根目录执行）：

```bash
curl -fL 'https://github.com/zhizhezhang/hurb-classification/releases/download/model-run02-epoch8-f1f2c67/convnext_tiny_best.pt' -o models/convnext_tiny_best.pt
printf '%s  %s\n' '202072243d01e7e47a4e008e0e6480d5446a2124f48f8512cca1ea3b379e814f' 'models/convnext_tiny_best.pt' | sha256sum -c -
```

| 环境变量 | 作用与默认值 |
| --- | --- |
| `HERB_MODEL_PATH` | 模型权重；默认 `models/convnext_tiny_best.pt` |
| `HERB_DEVICE` | `auto`（优先 CUDA）、`cpu` 或 `cuda` |
| `HERB_HISTORY_DB_PATH` | SQLite 文件；默认 `backend/runtime/history.db` |
| `HERB_UPLOADS_DIR` | 上传目录；默认 `backend/runtime/uploads/` |
| `DEEPSEEK_API_KEY` | 可选；DeepSeek AI 请求需要，不能写入 Git |
| `DEEPSEEK_MODEL` | 默认 `deepseek-flash` |
| `HERB_API_PROXY_TARGET` | Vite 的 `/api` 代理；默认 `http://127.0.0.1:8000` |

设置密钥时只在后端进程环境中配置，不放进前端或已跟踪文件；不要打印或记录密钥。无密钥时知识库、图鉴、模型分析、识别和历史仍可运行，DeepSeek AI 的模型请求返回 HTTP 503。

## 3. 启动与验证

在**仓库根目录**启动后端：

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

新终端在 `frontend/` 启动开发前端：

```powershell
Set-Location .\frontend
npm run dev
```

浏览器访问 `http://127.0.0.1:5173/recognition`。`GET http://127.0.0.1:8000/api/health` 检查模型状态，`/docs` 查看 OpenAPI。若端口已被占用，选择空闲端口并将 `HERB_API_PROXY_TARGET` 与后端端口配套设置；不要停止未知进程。识别上传、图鉴、历史与聊天的 API 均经过 `/api`。

## 4. 测试和常见问题

在仓库根目录运行后端全量测试；测试使用 Mock，不调用真实 DeepSeek。模型相关测试需要权重，部分预测测试还需要本地原始数据集。环境缺少这些文件时不能把受阻的用例算作通过。

```powershell
python -m unittest discover -s backend/tests -v
node --test frontend/tests/*.test.js
Set-Location .\frontend
npm run build
```

若 shell 的通配符行为不同，可在 `frontend/` 显式列出 `tests/*.test.js` 中的测试文件。缺权重时先按第 2 节准备；缺 API Key 时只影响外部问答；前端请求失败时核对后端端口和 `HERB_API_PROXY_TARGET`。首次启动会加载权重、图鉴、Skill 与评估归档，并初始化本地历史。生产构建生成静态资源，但本仓库未提供已验证的生产托管与反向代理配置。
