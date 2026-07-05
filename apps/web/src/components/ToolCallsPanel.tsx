import type { ToolCall } from "../api/types";
import { StatusBadge } from "./StatusBadge";

type ToolCallsPanelProps = {
  calls: ToolCall[];
};

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function formatDuration(call: ToolCall): string | null {
  if (!call.started_at || !call.finished_at) {
    return null;
  }
  const started = new Date(call.started_at).getTime();
  const finished = new Date(call.finished_at).getTime();
  if (Number.isNaN(started) || Number.isNaN(finished) || finished < started) {
    return null;
  }
  return `${finished - started} ms`;
}

export function ToolCallsPanel({ calls }: ToolCallsPanelProps) {
  if (calls.length === 0) {
    return <p className="text-sm text-slate-400">暂无工具调用</p>;
  }

  return (
    <div className="space-y-3">
      {calls.map((call) => {
        const duration = formatDuration(call);
        return (
          <article key={call.id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm font-medium text-slate-100">{call.tool_name}</span>
              <StatusBadge status={call.error ? "failed" : "succeeded"} />
              {duration && <span className="text-xs text-slate-500">{duration}</span>}
            </div>
            {call.started_at && (
              <p className="mt-1 text-xs text-slate-500">
                {new Date(call.started_at).toLocaleString()}
              </p>
            )}
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <h4 className="text-xs font-medium uppercase text-slate-500">参数</h4>
                <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-300">
                  {formatJson(call.arguments)}
                </pre>
              </div>
              <div>
                <h4 className="text-xs font-medium uppercase text-slate-500">
                  {call.error ? "错误" : "结果"}
                </h4>
                <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-300">
                  {call.error ?? call.result_summary ?? "无结果摘要"}
                </pre>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
