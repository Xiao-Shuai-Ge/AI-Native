# AI Native 多智能体协作平台

Day 3 交付：任务状态持久化、PostgreSQL 业务存储、Dapr State/Pub/Sub、Redis 会话上下文、任务 CRUD API。

## 前置条件

- Docker Desktop（或 Docker Engine + Compose）
- [uv](https://docs.astral.sh/uv/)（Python 3.12+）
- Node.js 20+
- [Dapr CLI](https://docs.dapr.io/getting-started/install-dapr-cli/)（本地开发可选）

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

### 3. 数据库迁移

```powershell
uv sync
uv run --directory apps/api alembic upgrade head
```

若之前跑过集成测试、表已存在但 Alembic 未记录版本，会报 `relation "tasks" already exists`。此时只需标记当前 schema 版本（不重复建表）：

```powershell
uv run --directory apps/api alembic stamp head
```

全新环境或需重置数据库时，可先清空再迁移：

```powershell
docker compose down -v postgres
docker compose up -d postgres
uv run --directory apps/api alembic upgrade head
```

### 4. 启动 API（本地 + Dapr sidecar）

**方式 A：dapr run（需先安装 [Dapr CLI](https://docs.dapr.io/getting-started/install-dapr-cli/)）**

macOS / Linux（zsh / bash，注意用 `\` 换行，不要用 PowerShell 的 `` ` ``）：

```bash
cd apps/api
uv run dapr run \
  --app-id api \
  --app-port 8000 \
  --dapr-http-port 3500 \
  --components-path ../../dapr/components \
  --config ../../dapr/config/config.yaml \
  -- uv run uvicorn api.main:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

或单行：

```bash
cd apps/api && uv run dapr run --app-id api --app-port 8000 --dapr-http-port 3500 --components-path ../../dapr/components --config ../../dapr/config/config.yaml -- uv run uvicorn api.main:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

Windows PowerShell：

```powershell
uv run --directory apps/api dapr run `
  --app-id api `
  --app-port 8000 `
  --dapr-http-port 3500 `
  --components-path ../../dapr/components `
  --config ../../dapr/config/config.yaml `
  -- uv run uvicorn api.main:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

**方式 B：Docker Compose（未安装 Dapr CLI 时推荐）**

```bash
docker compose up -d --build api api-daprd
```

**方式 C：仅 API（无 Dapr，Day 3 State/Pub/Sub 不可用）**

```bash
uv run --package api uvicorn api.main:app --app-dir apps/api/src --reload --host 0.0.0.0 --port 8000
```

验证：

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/api/providers
```

### 5. 任务 API（Day 3）

创建任务（异步 runner 会推进 `queued → running → succeeded`）：

```powershell
curl -X POST http://localhost:8000/api/tasks `
  -H "Content-Type: application/json" `
  -d '{"user_query":"什么是 Dapr State Management","engine":"auto","session_id":"22222222-2222-2222-2222-222222222222"}'
```

查询任务详情与历史：

```powershell
curl http://localhost:8000/api/tasks/{task_id}
curl http://localhost:8000/api/tasks
```

用户结构化偏好（新 session 可读）：

```powershell
curl -X PUT http://localhost:8000/api/users/default/preferences `
  -H "Content-Type: application/json" `
  -d '{"preferences":{"language":"zh-CN","report_format":"markdown"}}'
curl http://localhost:8000/api/users/default/preferences
```

Dapr Pub/Sub 订阅端点（sidecar 自动发现）：

```powershell
curl http://localhost:8000/dapr/subscribe
```

### 6. Writer 单 Agent 演示（Day 2）

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

### 7. 启动前端骨架（可选）

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

集成测试（需 Compose 运行 Redis + PostgreSQL）：

```powershell
uv run pytest apps/api/tests -q -m integration
```

真实 LLM smoke test（需 DeepSeek key 或本地 Ollama）：

```powershell
uv run pytest apps/api/tests -q -m smoke
```

## 目录结构

```text
apps/api/          FastAPI 后端（persistence、events、tasks API）
apps/mcp-server/   MCP Server 占位
apps/web/          React + Vite 前端骨架
dapr/              Dapr 组件与配置模板
infra/             Prometheus、Dockerfile 等基础设施配置
compose.yaml       中间件 + API + Dapr sidecar 编排
```

## Dapr 组件

Dapr 组件模板位于 `dapr/components/`。Day 3 起通过 sidecar 接入 State（`statestore`）与 Pub/Sub（`pubsub`）。LangGraph checkpoint 使用 `DaprCheckpointSaver` 写入 Dapr State。

## 开发规范

详见 [AGENTS.md](./AGENTS.md) 与 [开发执行计划.md](./开发执行计划.md)。
