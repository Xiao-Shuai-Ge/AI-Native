# AI Native 多智能体协作平台

Day 2 交付：统一 LLMClient、四供应商 adapter、writer 单 Agent 原型与开发演示 API。

## 前置条件

- Docker Desktop（或 Docker Engine + Compose）
- [uv](https://docs.astral.sh/uv/)（Python 3.12+）
- Node.js 20+

## 快速开始

### 1. 配置环境变量

```powershell
Copy-Item .env.example .env
```

编辑 `.env` 填入所需密钥。**所有密钥只从环境变量读取**，不要将真实 `.env` 提交到仓库。

### 2. 启动基础设施

```powershell
docker compose up -d redis postgres jaeger prometheus
docker compose ps
```

服务端口（默认值）：

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| Redis | 6379 | Dapr state / pub-sub |
| PostgreSQL | 5432 | 业务数据 |
| Jaeger UI | 16686 | 分布式追踪 |
| Jaeger OTLP | 4317 | OTLP gRPC |
| Prometheus | 9090 | 指标 |

### 3. 安装并启动 API

```powershell
uv sync
uv run --package api uvicorn api.main:app --app-dir apps/api/src --reload --host 0.0.0.0 --port 8000
```

验证：

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/api/providers
```

### 4. Writer 单 Agent 演示（Day 2）

在 `.env` 中配置 LLM 供应商后，可通过开发接口生成 Markdown 摘要：

```powershell
curl -X POST http://localhost:8000/api/dev/writer/summarize `
  -H "Content-Type: application/json" `
  -d '{"topic":"什么是 Dapr Workflow"}'
```

切换模型供应商时**只需修改环境变量**，无需改动 Agent 代码：

| 目标 | 环境变量 |
| --- | --- |
| DeepSeek（开发期默认） | `LLM_PROVIDER=deepseek`，并设置 `DEEPSEEK_API_KEY` |
| Ollama 本地模型 | `LLM_PROVIDER=ollama`，确保 `OLLAMA_BASE_URL` 与 `OLLAMA_MODEL` 可用 |
| OpenAI | `LLM_PROVIDER=openai`，并设置 `OPENAI_API_KEY` |
| Claude | `LLM_PROVIDER=anthropic`（或 `claude`），并设置 `ANTHROPIC_API_KEY` |

可选弹性参数：`LLM_TIMEOUT_SECONDS`（默认 60）、`LLM_MAX_RETRIES`（默认 1）。

### 5. 启动前端骨架（可选）

```powershell
npm --prefix apps/web install
npm --prefix apps/web run dev
```

## 质量检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy apps/api/src apps/mcp-server/src
uv run pytest apps/api/tests apps/mcp-server/tests -q -m "not integration and not smoke and not network"

npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run test
npm --prefix apps/web run build
```

集成测试（需 Compose 运行）：

```powershell
uv run pytest apps/api/tests -q -m integration
```

真实 LLM smoke test（需 DeepSeek key 或本地 Ollama）：

```powershell
uv run pytest apps/api/tests -q -m smoke
```

## 目录结构

```text
apps/api/          FastAPI 后端
apps/mcp-server/   MCP Server 占位
apps/web/          React + Vite 前端骨架
dapr/              Dapr 组件与配置模板
infra/             Prometheus 等基础设施配置
compose.yaml       Day 1 中间件编排
```

## Dapr 组件

Dapr 组件模板位于 `dapr/components/`，Day 1 仅作配置占位；从 Day 3 起接入 sidecar 与 Workflow。

## 开发规范

详见 [AGENTS.md](./AGENTS.md) 与 [开发执行计划.md](./开发执行计划.md)。
