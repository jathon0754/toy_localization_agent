# Toy Localization Agent (Multi-Agent MVP)

将玩具产品快速适配到目标市场（国家/地区），输出本土化方案、概念图和 3D 展示产物。

## 功能概览

- `CultureAgent`: 基于国家文化知识给出颜色、符号、禁忌和沟通风格建议。
- `RegulationAgent`: 输出目标市场玩具合规项与可落地改造建议。
- `DesignAgent`: 合并文化与法规输入，生成可执行设计修改方案。
- `CoordinatorAgent`: 产出结构化最终计划（动作清单、成本影响、实施步骤）。
- `PromptRefinerAgent`: 将文本方案重写为高质量图像提示词。
- `ImageGenAgent`: 生成概念图（失败自动回退 dummy 图）。
- `ThreeDGenAgent`: 生成 3D 展示（DreamGaussian 不可用时回退旋转 GIF）。

## 项目结构

```text
toy_localization_agent/
├── agents/                     # 各智能体实现
├── knowledge/
│   ├── data/                   # 市场知识文本（可用国家/地区码命名）
│   ├── build_kb.py             # 构建 Chroma 向量库
│   └── retriever.py            # 向量检索优先，文本回退
├── web/                        # Web 前端静态资源
├── examples/                   # 独立示例脚本
├── workflow.py                 # 核心编排逻辑（CLI/Web 共用）
├── main.py                     # CLI 入口
├── webapp.py                   # FastAPI Web 入口
├── .env.example                # 环境变量模板
└── requirements.txt            # 顶层依赖
```

## 环境要求

- Python `>=3.9,<3.13`

## 安装

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

可选（开发模式安装）:

```bash
pip install -e .
```

安装后可用命令：

- `toy-localization`（等价于 `python main.py`）
- `toy-localization-web`（等价于 `python webapp.py`）

## 配置

```bash
cp .env.example .env
```

必填：

（任选其一）

- `LLM_API_KEY`（推荐）
- `OPENAI_API_KEY`（兼容）
- `DEEPSEEK_API_KEY`（兼容）

可选：

- `LLM_API_BASE` / `OPENAI_API_BASE`
- `LLM_MODEL`
- `LLM_WIRE_API`（`responses` / `chat_completions`）
- `LLM_REASONING_EFFORT`
- `LLM_DISABLE_RESPONSE_STORAGE`
- `LLM_TEMPERATURE`
- `LLM_ENABLE_CACHE`
- `LLM_CACHE_DIR`
- `LLM_MAX_RETRIES`
- `LLM_RETRY_BACKOFF_SECONDS`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_OUTPUT_TOKENS`
- `EMBEDDING_MODEL`
- `DASHSCOPE_API_KEY`
- `IMAGE_GEN_MODEL`
- `IMAGE_GEN_SIZE`
- `CHROMA_PERSIST_DIR`
- `OUTPUT_DIR`
- `WEB_JOB_TTL_SECONDS`
- `WEB_MAX_JOBS`
- `WEB_MAX_CONCURRENT_JOBS`

## 使用方式

### 1) 仅文本方案（先验证主链路）

```bash
python main.py \
  --country japan \
  --description "一款会发光、可拼装的机器人玩具" \
  --skip-vision
```

### 2) 文本 + 概念图 + 3D

```bash
python main.py \
  --country usa \
  --description "一款儿童编程积木车，支持语音控制" \
  --auto-3d
```

说明：

- `--country` 会自动转小写（例如 `USA -> usa`）。
- 不传 `--auto-3d` 时，CLI 会交互确认是否生成 3D。
- `--target-language` 可覆盖输出语言（如 `zh`、`en`、`ja`），默认跟随市场/描述自动判断。
- `--allow-incomplete` 允许缺失关键信息时继续（默认会阻塞并提示补全）。
- `--non-interactive` 关闭缺失信息的交互式补全提示。
- `--channel` 传入渠道（如 `ecommerce` / `retail` / `gift`）。
- `--price-band` 传入价格带（如 `budget` / `mid` / `premium`）。
- `--material-constraints` / `--supplier-constraints` / `--cost-ceiling` 传入供应链约束。

### 3) 启动 Web 前端

```bash
python webapp.py
```

默认地址：`http://127.0.0.1:7860`

说明：

- Web 端默认使用异步任务接口（`POST /api/run_async` + `GET /api/jobs/{job_id}`）轮询日志与结果。
- 目标市场支持自定义添加（国家/地区码）；右侧结果区为“卡片翻看”布局，可点击标签/左右箭头切换。
- 每次运行完成后会写入生成历史：`outputs/history/<job_id>.json`，在 Web 的「历史」卡片可回看并加载结果。

## 知识库维护

### 新增市场知识（国家/地区）

在 `knowledge/data/` 添加 `<market>.txt`，例如：

- `knowledge/data/germany.txt`
- `knowledge/data/hk.txt`
- `knowledge/data/us-ca.txt`

可选：在文件开头添加元数据行（以 `#` 开头），用于注明更新时间与来源，例如：

```
# last_updated: 2026-03-14
# sources: internal draft; verify with official standards
# coverage: culture, compliance (high-level)
```

如果不存在对应文件，系统仍可运行（会使用通用参考并提示需要验证）。

### 构建向量库

```bash
python knowledge/build_kb.py
python knowledge/build_kb.py --country japan
```

常用参数：

- `--chunk-size`（默认 `200`）
- `--chunk-overlap`（默认 `20`）

检索逻辑：

- 若存在 `chroma_db/<country>/chroma.sqlite3`，优先向量检索。
- 否则回退读取 `knowledge/data/<country>.txt`。

## 输出说明

默认写入 `outputs/<run_id>/`（每次运行隔离）：

- `concept_<hash>.png`: 概念图
- `dummy_<hash>.png`: 图像生成失败时回退图
- `preview_turntable_<hash>.gif`: 3D 引擎不可用时的预览
- `3d/video.mp4`: DreamGaussian 成功产物

## 示例脚本

`examples/dashscope/image_edit_example.py` 是独立 DashScope 图像编辑示例，不参与主流程。

## 质量检查

```bash
python -m compileall -q .
python -m unittest discover -s tests -p 'test_*.py'
```

说明：`chroma_db/` 与 `outputs/` 属于运行时产物，默认不纳入版本控制。

## 当前状态

当前是可运行 MVP，已具备端到端流程与失败回退机制。生产化建议继续补充：

- 自动化测试覆盖
- 更细粒度国家法规知识
- DreamGaussian 标准化部署脚本
- 成本、时延、重试和可观测性策略
