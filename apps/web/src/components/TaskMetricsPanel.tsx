import { formatEngine } from "../lib/labels";
import type { TaskMetrics } from "../api/types";

type TaskMetricsPanelProps = {
  metrics: TaskMetrics;
  engine: string | null;
};

function formatTokenValue(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return value.toLocaleString();
}

export function TaskMetricsPanel({ metrics, engine }: TaskMetricsPanelProps) {
  const { token_usage: tokens } = metrics;
  const tokenKnown = tokens.status !== "unknown";

  return (
    <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
        <dt className="text-xs uppercase text-slate-500">工具调用总数</dt>
        <dd className="mt-1 text-2xl font-semibold text-slate-100">{metrics.tool_calls_total}</dd>
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
        <dt className="text-xs uppercase text-slate-500">成功 / 失败</dt>
        <dd className="mt-1 text-2xl font-semibold text-slate-100">
          {metrics.tool_calls_succeeded}
          <span className="mx-1 text-slate-500">/</span>
          {metrics.tool_calls_failed}
        </dd>
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
        <dt className="text-xs uppercase text-slate-500">输入 Token</dt>
        <dd className="mt-1 text-2xl font-semibold text-slate-100">
          {tokenKnown ? formatTokenValue(tokens.prompt_tokens) : "未知"}
        </dd>
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
        <dt className="text-xs uppercase text-slate-500">输出 Token</dt>
        <dd className="mt-1 text-2xl font-semibold text-slate-100">
          {tokenKnown ? formatTokenValue(tokens.completion_tokens) : "未知"}
        </dd>
      </div>
      {tokenKnown && tokens.total_tokens !== null && (
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4 sm:col-span-2">
          <dt className="text-xs uppercase text-slate-500">Token 总计</dt>
          <dd className="mt-1 text-2xl font-semibold text-slate-100">
            {formatTokenValue(tokens.total_tokens)}
            {tokens.status === "partial" && (
              <span className="ml-2 text-xs font-normal text-amber-400">部分已知</span>
            )}
          </dd>
        </div>
      )}
      {engine && (
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4 sm:col-span-2">
          <dt className="text-xs uppercase text-slate-500">引擎</dt>
          <dd className="mt-1 font-mono text-sm text-slate-300">{formatEngine(engine)}</dd>
        </div>
      )}
    </dl>
  );
}
