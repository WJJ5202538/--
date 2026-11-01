# 文批 DocMark

上传 Word / PDF，下载带红色 `#` 批注的 Word。项目使用 **FastAPI + uv**，前端为原生 HTML/CSS/JavaScript，无构建步骤。

> 当前目录里没有找到你已经写好的两个模块（提取模块、批注模块），所以仓库先内置了一套**可运行的演示批改器**，用于验证上传、处理、下载全链路。接入真实模块只需要修改一个文件，见下文。

## 零额外配置

克隆后只需要 **uv** 和浏览器：

- 不需要 Node.js / npm，前端没有构建步骤
- 不需要数据库、Redis、消息队列
- 不需要 Word、WPS、LibreOffice 或 PDF 转换服务
- 不需要 API Key、模型账号或 `.env` 文件
- 所有路径都相对项目目录；运行时文件写入 `data/`，已被 `.gitignore` 排除
- Windows / macOS / Linux 使用同一套 Python 依赖，`uv.lock` 已锁定版本
- 启动脚本使用 `uv sync --locked`，避免不同机器解析出不同版本

## 已实现

- 拖拽或点击上传 `.docx` / `.pdf`，默认单文件上限 30 MB
- 上传后自动处理，前端轮询进度，处理完成即可下载
- 原 Word 内容、数字、排版不改写
- 在错误段落之后**另起一行**插入红色加粗批注，固定以 `#` 开头：

```text
# 计算有误：3 × 4 = 13，正确结果应为 12。
```

- 支持正文段落、表格单元格中的错误
- 生成独立的 `原文件名_批注.docx`，不覆盖原稿
- PDF 无法原位编辑，内置引擎会先转成可编辑 Word 批注稿
- 文件类型、大小、ZIP 解压体积、PDF 页数均有检查
- 全部测试通过（数学检测、DOCX/PDF 提取、批注、上传下载接口）

## 快速启动

前提：安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)。Python 3.11+ 由 uv 负责查找或下载，不要求系统预装特定版本。

### 1. 获取代码

```bash
git clone <你的 GitHub 仓库地址>
cd <仓库目录>
```

### 2. 安装依赖

```bash
uv sync --locked
```

### 3. 启动

Windows PowerShell：

```powershell
.\run.ps1
```

macOS / Linux：

```bash
sh run.sh
# 可选：chmod +x run.sh 后直接 ./run.sh
```

也可以不经过脚本，三个平台通用：

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

然后打开 <http://127.0.0.1:8000>。

开发时自动重载：

```powershell
.\run.ps1 -Reload
```

```bash
RELOAD=1 sh run.sh
```

如果 PowerShell 阻止运行脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

局域网调试时默认只监听 `127.0.0.1`，需要显式放开：

```powershell
.\run.ps1 -BindHost 0.0.0.0 -Port 8000
```

```bash
HOST=0.0.0.0 PORT=8000 sh run.sh
```

> 放开监听前请确认网络环境可信。项目没有内置登录鉴权。

## 构建与检查

这是一个**不需要前端构建**的 FastAPI 项目，静态 HTML/CSS/JS 由 FastAPI 直接提供。`uv sync --locked` 完成依赖安装即可运行。

提交前建议执行：

```bash
uv run ruff check app tests
uv run pytest
```

GitHub Actions 会在 Ubuntu、Windows、macOS 上自动执行同样的检查，无需在仓库里配置 Secrets 或 Variables。

## 接入已有模块

编辑 **`app/grading_adapter.py`** 中的 `grade()`，把内置调用替换成你的两个模块即可。上传、任务状态、下载、错误提示都不用改。

示例：

```python
from pathlib import Path

from app.grading_adapter import GradeResult


def grade(source: Path, output: Path, source_type: str) -> GradeResult:
    from my_extractor import extract_to_json
    from my_annotator import annotate_word

    # 1. 你的提取模块：得到 JSON（需要 Markdown 也可以在这里一并生成）
    extraction = extract_to_json(str(source))

    # 2. 你的批注模块：在原始 Word 上生成 output
    #    PDF 需要先由你的模块转换成 Word，或者继续使用内置 PDF 分支。
    issue_count = annotate_word(str(source), extraction, str(output))

    return GradeResult(
        engine="我的批改模块",
        issue_count=issue_count,  # 拿不到数量可省略或传 None
        extraction=None,          # 可选，传内置 ExtractedDocument 才会保存调试副产物
    )
```

约定：

- `source`：用户上传的原文件，扩展名是 `.docx` 或 `.pdf`
- `output`：最终供用户下载的 `.docx`，必须由你的代码写入
- `source_type`：`"docx"` 或 `"pdf"`
- 失败时抛出异常，异常文本会直接显示在前端；请使用用户能看懂的中文
- `GradeResult.issue_count` 可为 `None`，前端会显示“批注稿已生成，可立即下载”
- `GradeResult.extraction` 可为 `None`。如果传入，服务端会把 JSON/Markdown 另存到 `data/outputs/` 便于排查

如果你的模块是命令行程序，也可以在这里用 `subprocess.run` 包一层；只要最终在 `output` 路径生成有效 DOCX 即可。

## 内置演示引擎的边界

演示引擎只检查**明确写出了等号和数字结果**的四则运算，例如：

- `3 × 4 = 13` → 报错
- `(1 + 2) × 3 = 8` → 报错
- `0.1 + 0.2 = 0.3` → 正确，不报错
- `1,000 + 2 = 1002` → 不当作表达式，避免误报

它不会做：变量方程、分式/根号/函数、跨行公式、应用题逻辑推理、手写 OCR。正式批改请接入你的两个模块。

PDF 的额外限制：

- 只提取可复制的文字；扫描版 PDF 需要先 OCR
- 内置引擎会把文字重排为新的 Word，不能保留 PDF 原版式
- 如果你的 PDF 模块能输出更好的 Word，直接在适配层调用它

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/jobs` | multipart 字段 `file`，返回 202 和任务 ID |
| `GET` | `/api/jobs/{id}` | 查询 `queued` / `processing` / `completed` / `failed` |
| `GET` | `/api/jobs/{id}/download` | 下载批注 Word |
| `GET` | `/api/config` | 前端读取大小限制和引擎名称 |
| `GET` | `/api/health` | 健康检查 |

上传响应示例：

```json
{
  "id": "e1dd511f58fc4a7d89735a69478179b7",
  "original_name": "课堂练习.docx",
  "status": "queued",
  "download_url": null
}
```

## 配置

通过环境变量调整：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DOCMARK_MAX_UPLOAD_MB` | `30` | 单文件上限（MB） |
| `DOCMARK_DATA_DIR` | `./data` | 上传文件和产物的根目录 |

所有配置都有默认值，**不设置也能直接运行**。需要修改时：

Windows PowerShell：

```powershell
$env:DOCMARK_MAX_UPLOAD_MB = "50"
$env:DOCMARK_DATA_DIR = ".\runtime-data"
.\run.ps1
```

macOS / Linux：

```bash
DOCMARK_MAX_UPLOAD_MB=50 DOCMARK_DATA_DIR=./runtime-data sh run.sh
```

`DOCMARK_DATA_DIR` 可以是相对项目目录的路径，也可以是绝对路径。

## 上传到 GitHub

仓库已经按“克隆即用”准备好，上传时注意：

- 必须提交 `pyproject.toml`、`uv.lock`、`app/`、`tests/`、`run.ps1`、`run.sh`
- `.venv/`、`data/uploads/`、`data/outputs/` 由 `.gitignore` 排除，不要提交
- 不需要在 GitHub 配置 Secrets、Variables、数据库或任何云服务
- 推送到 GitHub 后，`.github/workflows/ci.yml` 会自动在 Ubuntu、Windows、macOS 上跑 lint 和测试

如果使用命令行上传：

```bash
git init
git add .
git status --short
git commit -m "Initial commit"
git branch -M main
git remote add origin <你的仓库地址>
git push -u origin main
```

提交前建议先确认：

```bash
git status --ignored --short
```

输出里不应出现 `.venv/`、`data/uploads/`、`data/outputs/` 中的实际业务文件。

## 数据与安全

- 上传文件保存在 `data/uploads/`，批注稿和 JSON/Markdown 副产物保存在 `data/outputs/`
- 文件不会通过静态目录暴露；只有完成任务且持有 32 位任务 ID 才能下载
- 下载响应使用 `no-store`，并设置 `nosniff`、`X-Frame-Options`、CSP 等响应头
- 当前**不会自动清理**历史文件，请按需删除 `data/uploads` 和 `data/outputs` 中的内容
- 任务状态保存在内存中，服务重启后旧任务查询/下载会失效；原文件仍在磁盘上，但新进程不会再关联它们
- 仅面向本机或受信任内网。公网部署前请补充登录鉴权、HTTPS、限流、病毒扫描和持久化任务队列

## 测试

```bash
uv run ruff check app tests
uv run pytest
```

覆盖：

- 四则运算错误识别、全角符号、负数、除零、重复错误去重
- DOCX 段落和表格批注，确认原文未被改写、批注为红色
- PDF 文本提取并生成可编辑批注 Word
- 真实接口上传、轮询、下载、中文文件名、非法文件拒绝

本地验证记录：

- Windows 11 + Python 3.13：`uv sync --locked`、lint、14 项测试全部通过
- Linux（WSL Ubuntu）+ 全新项目副本 + Python 3.13：同上全部通过
- 两个平台的启动脚本均实际启动服务并通过 `/api/health` 检查
- GitHub Actions 额外覆盖 Ubuntu 的 Python 3.11 / 3.13，以及 Windows / macOS 的 Python 3.13

## 目录

```text
.github/workflows/ci.yml  Ubuntu / Windows / macOS 自动测试
app/
  main.py                 FastAPI 路由、安全上传、下载
  grading_adapter.py      ★ 接入你的两个模块的地方
  jobs.py                 内存任务状态
  services/
    extractor.py          DOCX/PDF → JSON + Markdown（演示）
    mathcheck.py          四则运算核对（演示）
    annotator.py          插入红色 # 批注（演示）
    pipeline.py           后台任务与产物落盘
  static/                 前端页面、样式、交互（无需构建）
tests/                    自动化测试
data/                     运行时文件（业务文件不入库）
run.ps1 / run.sh          跨平台启动脚本
pyproject.toml            依赖与工具配置
uv.lock                   锁定依赖，保证可复现
```

## 为什么只保留一个进程

任务状态在进程内存里，所以请使用单个 Uvicorn worker：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

不要加 `--workers 4`。如果要做多实例部署，应把 `JobStore` 换成 Redis/数据库，并把处理任务交给 Celery/RQ 等队列。
