import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { pauseTask, resumeTask } from "../api/tasks";
import { ReportViewer } from "../components/ReportViewer";
import { StatusBadge } from "../components/StatusBadge";
import { StepTimeline } from "../components/StepTimeline";
import { ToolCallsPanel } from "../components/ToolCallsPanel";
import { useTaskEvents } from "../hooks/useTaskEvents";

export function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const { task, auditEvents, loading, error, connectionMode, refresh } = useTaskEvents(taskId);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  async function handlePause() {
    if (!taskId) {
      return;
    }
    setActionLoading(true);
    setActionError(null);
    try {
      await pauseTask(taskId);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "暂停失败");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleResume() {
    if (!taskId) {
      return;
    }
    setActionLoading(true);
    setActionError(null);
    try {
      await resumeTask(taskId);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "恢复失败");
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) {
    return <p className="text-slate-400">加载任务详情...</p>;
  }

  if (error) {
    return (
      <div className="space-y-3">
        <p className="text-rose-300">加载失败：{error}</p>
        <Link to="/" className="text-sm text-sky-400 hover:underline">
          返回新建任务
        </Link>
      </div>
    );
  }

  if (!task) {
    return <p className="text-slate-400">任务不存在</p>;
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">任务详情</p>
          <h2 className="mt-1 text-2xl font-semibold">{task.user_query}</h2>
          <p className="mt-2 font-mono text-xs text-slate-500">{task.task_id}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={task.status} />
          <span className="text-xs text-slate-500">
            {connectionMode === "sse"
              ? "SSE 实时"
              : connectionMode === "polling"
                ? "轮询降级"
                : "已结束"}
          </span>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <h3 className="text-sm font-medium text-slate-300">编排信息</h3>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">请求模式</dt>
              <dd>{task.engine_requested}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">实际模式</dt>
              <dd>{task.engine_selected ?? "待定"}</dd>
            </div>
            {task.engine_selection_reason && (
              <div>
                <dt className="text-slate-500">自动选择原因</dt>
                <dd className="mt-1 text-slate-300">{task.engine_selection_reason}</dd>
              </div>
            )}
          </dl>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <h3 className="text-sm font-medium text-slate-300">任务控制</h3>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => void handlePause()}
              disabled={actionLoading || task.status !== "running"}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800 disabled:opacity-50"
            >
              暂停
            </button>
            <button
              type="button"
              onClick={() => void handleResume()}
              disabled={actionLoading || task.status !== "paused"}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800 disabled:opacity-50"
            >
              恢复
            </button>
          </div>
          {actionError && <p className="mt-2 text-sm text-rose-300">{actionError}</p>}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
        <h3 className="text-lg font-medium">Agent 时间线</h3>
        <div className="mt-4">
          <StepTimeline events={auditEvents} />
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
        <h3 className="text-lg font-medium">工具调用</h3>
        <div className="mt-4">
          <ToolCallsPanel calls={task.tool_calls} />
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
        <h3 className="text-lg font-medium">最终报告</h3>
        <div className="mt-4">
          <ReportViewer report={task.report} />
        </div>
      </div>
    </section>
  );
}
