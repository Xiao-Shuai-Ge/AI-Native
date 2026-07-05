import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getSettings, updateSettings } from "../api/settings";
import { listTasks } from "../api/tasks";
import type { AgentRoleSettings, RuntimeSettings, TaskSummary } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { formatAgentField, formatAgentKey, formatEngine } from "../lib/labels";

const AGENT_KEYS = ["researcher", "analyst", "writer"] as const;
const LLM_PROVIDERS = ["deepseek", "ollama", "openai", "anthropic", "claude"] as const;

type Tab = "history" | "settings";

export function HistorySettingsPage() {
  const [tab, setTab] = useState<Tab>("history");
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [taskList, runtimeSettings] = await Promise.all([listTasks(), getSettings()]);
        if (!cancelled) {
          setTasks(taskList);
          setSettings(runtimeSettings);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  function updateAgentField(
    key: string,
    field: keyof AgentRoleSettings,
    value: string | number,
  ) {
    setSettings((prev) => {
      if (!prev) {
        return prev;
      }
      return {
        ...prev,
        agents: {
          ...prev.agents,
          [key]: {
            ...prev.agents[key],
            [field]: value,
          },
        },
      };
    });
  }

  async function handleSaveSettings() {
    if (!settings) {
      return;
    }
    setSaving(true);
    setSaveMessage(null);
    setError(null);
    try {
      const updated = await updateSettings(settings);
      setSettings(updated);
      setSaveMessage("设置已保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="space-y-6">
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setTab("history")}
          className={`rounded-lg px-3 py-2 text-sm ${
            tab === "history" ? "bg-slate-800 text-white" : "text-slate-400"
          }`}
        >
          历史任务
        </button>
        <button
          type="button"
          onClick={() => setTab("settings")}
          className={`rounded-lg px-3 py-2 text-sm ${
            tab === "settings" ? "bg-slate-800 text-white" : "text-slate-400"
          }`}
        >
          角色与模型设置
        </button>
      </div>

      {loading && <p className="text-slate-400">加载中...</p>}
      {error && <p className="text-rose-300">{error}</p>}

      {!loading && tab === "history" && (
        <div className="space-y-3">
          {tasks.length === 0 ? (
            <p className="text-slate-400">暂无历史任务</p>
          ) : (
            tasks.map((task) => (
              <Link
                key={task.task_id}
                to={`/tasks/${task.task_id}`}
                className="block rounded-2xl border border-slate-800 bg-slate-900/70 p-4 hover:border-slate-700"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-medium text-slate-100">{task.user_query}</h3>
                  <StatusBadge status={task.status} />
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  {formatEngine(task.engine_requested)}
                  {task.engine_selected ? ` → ${formatEngine(task.engine_selected)}` : ""} ·{" "}
                  {new Date(task.created_at).toLocaleString()}
                </p>
              </Link>
            ))
          )}
        </div>
      )}

      {!loading && tab === "settings" && settings && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
            <h3 className="text-lg font-medium">模型参数</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">模型供应商</span>
                <select
                  value={settings.llm.provider}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      llm: { ...settings.llm, provider: event.target.value },
                    })
                  }
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
                >
                  {LLM_PROVIDERS.map((provider) => (
                    <option key={provider} value={provider}>
                      {provider}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">温度</span>
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={settings.llm.temperature}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      llm: { ...settings.llm, temperature: Number(event.target.value) },
                    })
                  }
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">最大 Token 数</span>
                <input
                  type="number"
                  min={1}
                  value={settings.llm.max_tokens}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      llm: { ...settings.llm, max_tokens: Number(event.target.value) },
                    })
                  }
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
                />
              </label>
            </div>
          </div>

          {AGENT_KEYS.map((key) => {
            const agent = settings.agents[key];
            if (!agent) {
              return null;
            }
            return (
              <div
                key={key}
                className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6"
              >
                <h3 className="text-lg font-medium">{formatAgentKey(key)}</h3>
                <div className="mt-4 grid gap-3">
                  {(["role", "goal", "backstory", "instructions"] as const).map((field) => (
                    <label key={field} className="space-y-1 text-sm">
                      <span className="text-slate-400">{formatAgentField(field)}</span>
                      <textarea
                        rows={field === "instructions" ? 3 : 2}
                        value={agent[field]}
                        onChange={(event) => updateAgentField(key, field, event.target.value)}
                        className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
                      />
                    </label>
                  ))}
                </div>
              </div>
            );
          })}

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void handleSaveSettings()}
              disabled={saving}
              className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              {saving ? "保存中..." : "保存设置"}
            </button>
            {saveMessage && <span className="text-sm text-emerald-300">{saveMessage}</span>}
          </div>
        </div>
      )}
    </section>
  );
}
