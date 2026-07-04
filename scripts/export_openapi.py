#!/usr/bin/env python3
"""Export OpenAPI spec for Apifox / Swagger import."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
DOCS = ROOT / "docs"

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from api.main import app  # noqa: E402


def build_spec() -> dict[str, object]:
    spec: dict[str, object] = app.openapi()
    spec["openapi"] = "3.0.3"
    spec["info"] = {
        "title": "AI Native API",
        "description": (
            "AI Native 多智能体协作平台 API（Day 3 交付）。\n\n"
            "已实现：健康检查、LLM 供应商查询、Writer 单 Agent 演示、"
            "任务 CRUD、用户偏好、Dapr Pub/Sub 订阅端点。\n\n"
            "Base URL 默认：http://localhost:8000\n"
            "启动：docker compose up -d --build api api-daprd"
        ),
        "version": "0.2.0",
    }
    spec["servers"] = [
        {"url": "http://localhost:8000", "description": "本地 Compose（api + daprd）"},
        {"url": "http://127.0.0.1:8000", "description": "本地直连"},
    ]
    tags = [
        {"name": "health", "description": "存活与就绪检查"},
        {"name": "providers", "description": "LLM 供应商与能力"},
        {"name": "dev-writer", "description": "Day 2 Writer 单 Agent 开发演示"},
        {"name": "tasks", "description": "Day 3 任务创建与查询"},
        {"name": "users", "description": "Day 3 用户结构化偏好"},
        {"name": "dapr", "description": "Dapr sidecar 订阅（通常由 sidecar 自动调用）"},
    ]
    spec["tags"] = tags
    return spec


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    spec = build_spec()

    json_path = DOCS / "openapi.json"
    json_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {json_path} ({len(spec.get('paths', {}))} paths)")

    try:
        import yaml

        yaml_path = DOCS / "openapi.yaml"
        yaml_path.write_text(
            yaml.dump(spec, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        print(f"Wrote {yaml_path}")
    except ImportError:
        print("PyYAML not installed; skipped openapi.yaml (JSON is enough for Apifox)")


if __name__ == "__main__":
    main()
