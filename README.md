# AI Native 多智能体协作平台

Day 1 交付：项目骨架、基础设施与健康检查接口。

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
```

### 4. 启动前端骨架（可选）

```powershell
npm --prefix apps/web install
npm --prefix apps/web run dev
```

## 质量检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy apps/api/src apps/mcp-server/src
uv run pytest apps/api/tests apps/mcp-server/tests -q -m "not integration"

npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run test
npm --prefix apps/web run build
```

集成测试（需 Compose 运行）：

```powershell
uv run pytest apps/api/tests -q -m integration
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
