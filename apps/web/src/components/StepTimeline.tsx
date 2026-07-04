import type { AuditEvent } from "../api/types";
import { StatusBadge } from "./StatusBadge";

type StepTimelineProps = {
  events: AuditEvent[];
};

export function StepTimeline({ events }: StepTimelineProps) {
  if (events.length === 0) {
    return <p className="text-sm text-slate-400">暂无步骤事件</p>;
  }

  return (
    <ol className="space-y-3 border-l border-slate-700 pl-4">
      {events.map((event) => (
        <li key={event.id} className="relative">
          <span className="absolute -left-[1.35rem] top-1.5 h-2 w-2 rounded-full bg-sky-400" />
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-slate-100">{event.step}</span>
            <StatusBadge status={event.status} />
            <span className="text-xs text-slate-500">{event.engine}</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {new Date(event.event_time).toLocaleString()}
          </p>
          {typeof event.payload.detail === "string" && event.payload.detail && (
            <p className="mt-1 text-sm text-slate-300">{event.payload.detail}</p>
          )}
        </li>
      ))}
    </ol>
  );
}
