"""Day 10 acceptance runner for the AI Native coursework project.

The script uses only the Python standard library so it can run from a fresh
checkout after the Compose stack is up. It verifies live HTTP behavior instead
of relying on static inspection.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    data: dict[str, Any] | None = None


def request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        return 0, {"error": str(exc)}


def check_endpoint(base_url: str, path: str, expected_status: int = 200) -> CheckResult:
    status, payload = request_json("GET", f"{base_url}{path}")
    ok = status == expected_status
    return CheckResult(path, ok, f"HTTP {status}", payload)


def wait_for_api(base_url: str, timeout_seconds: float) -> CheckResult:
    deadline = time.monotonic() + timeout_seconds
    last: CheckResult | None = None
    while time.monotonic() < deadline:
        last = check_endpoint(base_url, "/health")
        if last.ok:
            return CheckResult("api startup", True, "health endpoint is ready", last.data)
        time.sleep(1.0)
    detail = last.detail if last is not None else "not checked"
    data = last.data if last is not None else None
    return CheckResult("api startup", False, detail, data)


def create_task(base_url: str, *, user_query: str, engine: str, delay_seconds: float = 0.0) -> str:
    status, payload = request_json(
        "POST",
        f"{base_url}/api/tasks",
        payload={
            "user_query": user_query,
            "engine": engine,
            "delay_seconds": delay_seconds,
        },
        timeout=60.0,
    )
    if status != 201:
        raise RuntimeError(f"create task failed for {engine}: HTTP {status} {payload}")
    return str(payload["task_id"])


def wait_task(base_url: str, task_id: str, *, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status, payload = request_json("GET", f"{base_url}/api/tasks/{task_id}", timeout=30.0)
        if status != 200:
            raise RuntimeError(f"get task {task_id} failed: HTTP {status} {payload}")
        last_payload = payload
        if payload.get("status") in TERMINAL_STATUSES:
            return payload
        time.sleep(2.0)
    raise TimeoutError(f"task {task_id} did not finish in {timeout_seconds}s: {last_payload}")


def check_tools(base_url: str) -> CheckResult:
    status, payload = request_json("GET", f"{base_url}/api/tools")
    tools = payload.get("tools", []) if isinstance(payload, dict) else []
    names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
    expected = {"calculator", "web_search", "code_runner", "readonly_sql"}
    ok = status == 200 and expected.issubset(names)
    return CheckResult(
        "mcp tools",
        ok,
        f"HTTP {status}; discovered={sorted(name for name in names if name)}",
        payload,
    )


def run_engine_task(base_url: str, engine: str, timeout_seconds: float) -> CheckResult:
    started = time.monotonic()
    task_id = create_task(
        base_url,
        user_query=f"Day 10 acceptance: summarize Dapr Workflow with engine {engine}",
        engine=engine,
    )
    detail = wait_task(base_url, task_id, timeout_seconds=timeout_seconds)
    elapsed = time.monotonic() - started
    status = str(detail.get("status"))
    report = detail.get("report")
    metrics = detail.get("metrics") if isinstance(detail.get("metrics"), dict) else {}
    selected = detail.get("engine_selected")
    ok = status == "succeeded" and isinstance(report, str) and len(report) > 20
    return CheckResult(
        f"engine {engine}",
        ok,
        (
            f"task={task_id}; status={status}; selected={selected}; "
            f"elapsed={elapsed:.1f}s; tokens={metrics.get('token_usage')}"
        ),
        {
            "task_id": task_id,
            "status": status,
            "engine_selected": selected,
            "elapsed_seconds": round(elapsed, 2),
            "metrics": metrics,
            "steps": [step.get("step_name") for step in detail.get("steps", [])],
        },
    )


def run_concurrency(base_url: str, count: int, timeout_seconds: float) -> CheckResult:
    started = time.monotonic()

    def one(index: int) -> dict[str, Any]:
        task_id = create_task(
            base_url,
            user_query=f"Day 10 lightweight concurrent task {index}",
            engine="langgraph",
        )
        detail = wait_task(base_url, task_id, timeout_seconds=timeout_seconds)
        return {"task_id": task_id, "status": detail.get("status")}

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 10)) as pool:
        futures = [pool.submit(one, index) for index in range(count)]
        results: list[dict[str, Any]] = []
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - reported in the acceptance artifact
                results.append({"status": "error", "error": str(exc)})

    elapsed = time.monotonic() - started
    succeeded = sum(1 for item in results if item.get("status") == "succeeded")
    ok = succeeded == count
    return CheckResult(
        "lightweight concurrency",
        ok,
        f"{succeeded}/{count} succeeded in {elapsed:.1f}s",
        {"results": results, "elapsed_seconds": round(elapsed, 2)},
    )


def write_output(path: Path, results: list[CheckResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ok": all(result.ok for result in results),
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Day 10 live acceptance checks.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--quick", action="store_true", help="Only check health/readiness/tools.")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--startup-timeout", type=float, default=30.0)
    parser.add_argument("--concurrency", type=int, default=0)
    parser.add_argument(
        "--engines",
        default="langgraph,crewai,auto",
        help="Comma-separated engines to run in full mode.",
    )
    parser.add_argument("--output", default="docs/day10-acceptance-results.json")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    startup = wait_for_api(base_url, args.startup_timeout)
    results = [
        startup,
        check_endpoint(base_url, "/health"),
        check_endpoint(base_url, "/ready"),
        check_endpoint(base_url, "/api/providers"),
        check_tools(base_url),
    ]

    if not args.quick:
        for engine in [item.strip() for item in args.engines.split(",") if item.strip()]:
            results.append(run_engine_task(base_url, engine, args.timeout))
        if args.concurrency > 0:
            results.append(run_concurrency(base_url, args.concurrency, args.timeout))

    write_output(Path(args.output), results)
    for result in results:
        mark = "PASS" if result.ok else "FAIL"
        print(f"[{mark}] {result.name}: {result.detail}")
    print(f"wrote {args.output}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
