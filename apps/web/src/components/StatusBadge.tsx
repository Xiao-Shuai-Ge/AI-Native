import type { TaskStatus } from "../api/types";
import { formatStatus } from "../lib/labels";

const STATUS_STYLES: Record<TaskStatus, string> = {
  queued: "bg-slate-700 text-slate-200",
  running: "bg-sky-900 text-sky-200",
  paused: "bg-amber-900 text-amber-200",
  succeeded: "bg-emerald-900 text-emerald-200",
  failed: "bg-rose-900 text-rose-200",
  cancelled: "bg-slate-800 text-slate-400",
};

type StatusBadgeProps = {
  status: TaskStatus | string;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const style = STATUS_STYLES[status as TaskStatus] ?? "bg-slate-700 text-slate-200";
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {formatStatus(status)}
    </span>
  );
}
