import { jaegerTraceUrl, prometheusExploreUrl } from "../config/observability";
import type { TaskMetrics } from "../api/types";

type ObservabilityLinksProps = {
  metrics: TaskMetrics;
  engine: string | null;
};

export function ObservabilityLinks({ metrics, engine }: ObservabilityLinksProps) {
  const engineLabel = engine && engine !== "auto" ? engine : "langgraph|crewai";
  const toolCallsQuery = `sum by (engine, status) (tool_calls_total{engine=~"${engineLabel}"})`;
  const tokenQuery = `sum by (provider, token_type) (llm_tokens_total)`;

  return (
    <div className="mt-4 space-y-3 rounded-lg border border-slate-800 bg-slate-950/50 p-4">
      <h4 className="text-xs font-medium uppercase text-slate-500">可观测性</h4>
      <ul className="space-y-2 text-sm">
        {metrics.trace_id ? (
          <li>
            <a
              href={jaegerTraceUrl(metrics.trace_id)}
              target="_blank"
              rel="noreferrer"
              className="text-sky-400 hover:underline"
            >
              在 Jaeger 中查看 Trace（{metrics.trace_id.slice(0, 8)}…）
            </a>
          </li>
        ) : (
          <li className="text-slate-500">暂无 trace_id，任务运行后将出现在审计事件中</li>
        )}
        <li>
          <a
            href={prometheusExploreUrl(toolCallsQuery)}
            target="_blank"
            rel="noreferrer"
            className="text-sky-400 hover:underline"
          >
            Prometheus：工具调用成功率（按 engine）
          </a>
        </li>
        <li>
          <a
            href={prometheusExploreUrl(tokenQuery)}
            target="_blank"
            rel="noreferrer"
            className="text-sky-400 hover:underline"
          >
            Prometheus：LLM Token 用量（按 provider）
          </a>
        </li>
      </ul>
    </div>
  );
}
