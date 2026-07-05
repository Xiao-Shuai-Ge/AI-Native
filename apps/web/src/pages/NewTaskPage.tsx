import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getProviders } from "../api/providers";
import { createTask } from "../api/tasks";
import type { EngineChoice, LLMProviderInfo } from "../api/types";

const ENGINES: { value: EngineChoice; label: string }[] = [
  { value: "auto", label: "自动选择" },
  { value: "langgraph", label: "LangGraph（状态图编排）" },
  { value: "crewai", label: "CrewAI（角色协作编排）" },
];

export function NewTaskPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [engine, setEngine] = useState<EngineChoice>("auto");
  const [providerInfo, setProviderInfo] = useState<LLMProviderInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [providerLoading, setProviderLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadProvider() {
      setProviderLoading(true);
      try {
        const info = await getProviders();
        if (!cancelled) {
          setProviderInfo(info);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "无法加载模型供应商");
        }
      } finally {
        if (!cancelled) {
          setProviderLoading(false);
        }
      }
    }
    void loadProvider();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await createTask({ user_query: query.trim(), engine });
      navigate(`/tasks/${result.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建任务失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">新建研究任务</h2>
        <p className="mt-1 text-slate-400">输入主题，选择编排模式后提交。</p>
      </div>

      <form
        onSubmit={(event) => void handleSubmit(event)}
        className="space-y-5 rounded-2xl border border-slate-800 bg-slate-900/70 p-6"
      >
        <div className="space-y-2">
          <label htmlFor="user_query" className="text-sm font-medium text-slate-300">
            研究主题
          </label>
          <textarea
            id="user_query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            rows={4}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            placeholder="例如：比较 LangGraph 与 CrewAI 的适用场景"
            required
          />
        </div>

        <div className="space-y-2">
          <label htmlFor="engine" className="text-sm font-medium text-slate-300">
            编排模式
          </label>
          <select
            id="engine"
            value={engine}
            onChange={(event) => setEngine(event.target.value as EngineChoice)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          >
            {ENGINES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
          {providerLoading && <p>加载当前模型供应商...</p>}
          {!providerLoading && providerInfo && (
            <p>
              当前模型：<span className="text-slate-200">{providerInfo.provider}</span> /{" "}
              <span className="text-slate-200">{providerInfo.model}</span>
            </p>
          )}
          {!providerLoading && !providerInfo && <p>无法获取模型供应商信息</p>}
        </div>

        {error && <p className="text-sm text-rose-300">{error}</p>}

        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "提交中..." : "创建任务"}
        </button>
      </form>
    </section>
  );
}
