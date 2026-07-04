# AI Native 多智能体协作平台

Day 5～6 交付：Web 控制台（新建任务、详情 SSE/轮询、历史、设置）、`GET/PUT /api/settings`、`GET /api/tasks/{id}/events` SSE。

Day 4 交付：Dapr Workflow 耐久编排、独立 Worker、任务暂停/恢复、Worker 重启恢复演示、DurableAgent smoke test。

Day 3 能力仍保留：PostgreSQL 业务存储、Dapr State/Pub/Sub、Redis 会话上下文、任务 CRUD API。

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
| Web UI（Compose） | 5173 | React 控制台 |
| Web UI（本地 dev） | 5173 | `npm run dev`，代理到 API |

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

**本地 Workflow Worker（与 API 并行运行）**

```bash
cd apps/api && uv run dapr run --app-id worker --app-port 0 --dapr-http-port 3501 --dapr-grpc-port 50002 --components-path ../../dapr/components --config ../../dapr/config/config.yaml -- uv run python -m workflows.worker_main
```

本地 Worker 需使用与 API sidecar 不同的 Dapr 端口；创建任务时 API 的 `DAPR_GRPC_PORT` 与 Worker 的 sidecar 通过同一 Dapr 运行时共享 Workflow 任务队列（Compose 部署时无需手动区分端口）。

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
docker compose up -d --build api api-daprd worker worker-daprd placement scheduler
```

Compose 模式下 API 会通过 `WORKFLOW_DAPR_GRPC_HOST=worker` 将 Workflow 实例调度到
worker sidecar；`api-daprd` 仍负责 API 自身的 State、Pub/Sub、Service Invocation 和 ready
检查。`api` 也声明了 `worker-daprd` 依赖，单独启动 `api` 时 Compose 会拉起 Workflow
所需组件；显式列出完整集合便于演示时确认服务都在运行。

**Worker 水平扩展（Compose 限制）**

当前 Compose 使用 `worker-daprd` 的 `network_mode: service:worker`，每个 Worker 副本需要独立
sidecar；`docker compose up --scale worker=2` **不会**为第二个 Worker 自动挂载 Dapr sidecar。
Day 4 演示请保持单 Worker；多 Worker 水平扩展与重启恢复验收需在后续 Kubernetes 或自定义
Compose 编排中完成。

**方式 C：仅 API（无 Dapr，Workflow/State/Pub/Sub 不可用）**

```bash
uv run --package api uvicorn api.main:app --app-dir apps/api/src --reload --host 0.0.0.0 --port 8000
```

验证：

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/api/providers
```

### 5. 启动 Web 控制台

**本地开发（推荐，热更新）**

先确保 API 已启动（见上一节），然后：

```bash
cd apps/web
npm install
npm run dev
```

浏览器打开 http://localhost:5173 。Vite 已将 `/api`、`/health`、`/ready` 代理到 `http://localhost:8000`。

**Docker Compose**

```bash
docker compose up -d --build api api-daprd worker worker-daprd placement scheduler web
```

浏览器打开 http://localhost:5173 （或 `.env` 中 `WEB_PORT` 指定的端口）。

Web 控制台包含三个页面：

1. **新建任务** — 输入主题，选择 `自动 / LangGraph / CrewAI`，提交后跳转详情页。
2. **任务详情** — 状态、引擎选择原因、Agent 时间线（SSE 实时更新，断线后有限重连并降级轮询）、暂停/恢复、最终报告。
3. **历史与设置** — 历史任务列表；在线编辑三角色 role/goal/backstory/instructions 与模型 temperature/max_tokens。

> **SSE 限制**：任务事件 SSE 通过 API 进程内广播推送。请保持 **单个 API 实例**（默认 Compose 配置），或确保负载均衡对 `/api/tasks/*/events` 使用 sticky session；多 API 副本且无 sticky 时，SSE 可能收不到实时事件，详情页会自动降级为轮询。

### 6. 任务 API（Day 4 Workflow）

创建任务后 API **立即返回** `task_id`；Dapr Workflow Worker 异步执行 `plan → writer` stub 步骤。

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"user_query":"什么是 Dapr Workflow","engine":"auto"}'
```

带人为延迟的恢复演示（省略 `delay_seconds` 时使用环境变量 `TASK_DELAY_SECONDS`；显式传 `0` 可关闭延迟）：

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"user_query":"recovery demo","engine":"auto","delay_seconds":30}'
```

暂停与恢复：

```bash
curl -X POST http://localhost:8000/api/tasks/{task_id}/pause
curl -X POST http://localhost:8000/api/tasks/{task_id}/resume
```

查询任务详情与历史：

```bash
curl http://localhost:8000/api/tasks/{task_id}
curl http://localhost:8000/api/tasks
```

#### Worker 重启恢复演示

1. 创建带 `delay_seconds: 30` 的任务，记录 `task_id`。
2. 在延迟 Activity 运行期间执行 `docker compose stop worker`。
3. 执行 `docker compose start worker`。
4. 再次查询同一 `task_id`：状态应继续推进至 `succeeded`，已完成步骤不会重复入库（幂等键 `{task_id}:{step_name}`）。

也可通过环境变量为所有任务设置默认延迟（仅演示）：`TASK_DELAY_SECONDS=30`。

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

CrewAI 引擎默认会把自身的 kickoff 重放缓存（与本项目的 PostgreSQL/Redis 持久化无关）写到系统临时目录 `$TMPDIR/ainative-crewai-storage`，并关闭其默认的匿名遥测上报；如需覆盖，可显式设置环境变量 `CREWAI_STORAGE_DIR`（自定义持久化目录）或 `CREWAI_DISABLE_TELEMETRY=false`（重新开启遥测）。

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

DurableAgent smoke test（需 Dapr sidecar + conversation 组件，默认单元测试 mock 构建）：

```powershell
uv run pytest apps/api/tests/test_durable_agent_smoke.py -q
```

## 目录结构

```text
apps/api/          FastAPI 后端（persistence、events、workflows、tasks API）
apps/mcp-server/   MCP Server 占位
apps/web/          React + Vite 前端骨架
dapr/              Dapr 组件与配置模板
infra/             Prometheus、Dockerfile、worker entrypoint
compose.yaml       中间件 + API + Worker + Dapr sidecar 编排
```

## Dapr 组件

Dapr 组件模板位于 `dapr/components/`。Day 4 起 API 通过 Dapr Workflow 调度任务，Worker 注册 `task_orchestration` Workflow 与 Activity；State（`statestore`）与 Pub/Sub（`pubsub`）仍由 sidecar 提供。LangGraph checkpoint 使用 `DaprCheckpointSaver` 写入 Dapr State。

## 开发规范

详见 [AGENTS.md](./AGENTS.md) 与 [开发执行计划.md](./开发执行计划.md)。
