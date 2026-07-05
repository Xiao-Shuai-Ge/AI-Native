import { useEffect, useState } from "react";

import { listTools } from "../api/tools";
import type { ToolInfo } from "../api/types";

export function AvailableToolsPanel() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await listTools();
        if (!cancelled) {
          setTools(response.tools);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载工具列表失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <p className="text-sm text-slate-400">加载 MCP 工具列表...</p>;
  }

  if (error) {
    return <p className="text-sm text-rose-300">工具列表不可用：{error}</p>;
  }

  if (tools.length === 0) {
    return <p className="text-sm text-slate-400">暂无可用 MCP 工具</p>;
  }

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {tools.map((tool) => (
        <article key={tool.name} className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
          <h4 className="font-mono text-sm font-medium text-slate-100">{tool.name}</h4>
          <p className="mt-2 text-sm text-slate-400">{tool.description || "无描述"}</p>
        </article>
      ))}
    </div>
  );
}
