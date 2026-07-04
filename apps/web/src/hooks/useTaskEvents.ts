import { useCallback, useEffect, useRef, useState } from "react";

import { getTask, taskEventsUrl } from "../api/tasks";
import type { AuditEvent, TaskDetail, TaskEventSnapshot, TaskSseEvent, TaskStatus } from "../api/types";

const TERMINAL: TaskStatus[] = ["succeeded", "failed", "cancelled"];
const MAX_SSE_RECONNECTS = 3;
const POLL_INTERVAL_MS = 2000;

type UseTaskEventsResult = {
  task: TaskDetail | null;
  auditEvents: AuditEvent[];
  loading: boolean;
  error: string | null;
  connectionMode: "sse" | "polling" | "idle";
  refresh: () => Promise<void>;
};

function mergeAuditEvents(existing: AuditEvent[], incoming: AuditEvent[]): AuditEvent[] {
  const map = new Map(existing.map((event) => [event.id, event]));
  for (const event of incoming) {
    map.set(event.id, event);
  }
  return [...map.values()].sort(
    (a, b) => new Date(a.event_time).getTime() - new Date(b.event_time).getTime(),
  );
}

function sseEventToAudit(event: TaskSseEvent): AuditEvent {
  return {
    id: `${event.step}-${event.status}-${event.timestamp}`,
    engine: event.engine,
    step: event.step,
    status: event.status,
    payload: event.payload,
    event_time: event.timestamp,
  };
}

export function useTaskEvents(taskId: string | undefined): UseTaskEventsResult {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectionMode, setConnectionMode] = useState<"sse" | "polling" | "idle">("idle");

  const reconnectCount = useRef(0);
  const pollTimer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (!taskId) {
      return;
    }
    const detail = await getTask(taskId);
    setTask(detail);
    setAuditEvents(detail.audit_events);
  }, [taskId]);

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) {
      window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    if (!taskId || pollTimer.current !== null) {
      return;
    }
    setConnectionMode("polling");
    pollTimer.current = window.setInterval(() => {
      void refresh().catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "poll failed");
      });
    }, POLL_INTERVAL_MS);
  }, [refresh, taskId]);

  useEffect(() => {
    if (!taskId) {
      return undefined;
    }

    let cancelled = false;
    let closedGracefully = false;
    let eventSource: EventSource | null = null;

    const load = async () => {
      setLoading(true);
      setError(null);
      reconnectCount.current = 0;
      try {
        const detail = await getTask(taskId);
        if (cancelled) {
          return;
        }
        setTask(detail);
        setAuditEvents(detail.audit_events);
        if (TERMINAL.includes(detail.status)) {
          setConnectionMode("idle");
          setLoading(false);
          return;
        }

        const connectSse = () => {
          if (cancelled) {
            return;
          }
          setConnectionMode("sse");
          eventSource = new EventSource(taskEventsUrl(taskId));

          eventSource.addEventListener("snapshot", (message) => {
            const data = JSON.parse(message.data) as TaskEventSnapshot;
            setAuditEvents(data.audit_events);
          });

          eventSource.addEventListener("task_event", (message) => {
            const data = JSON.parse(message.data) as TaskSseEvent;
            setAuditEvents((prev) => mergeAuditEvents(prev, [sseEventToAudit(data)]));
            void refresh().catch(() => undefined);
          });

          eventSource.addEventListener("close", () => {
            closedGracefully = true;
            eventSource?.close();
            setConnectionMode("idle");
            void refresh().catch(() => undefined);
          });

          eventSource.onerror = () => {
            if (closedGracefully || cancelled) {
              return;
            }
            eventSource?.close();
            reconnectCount.current += 1;
            if (reconnectCount.current <= MAX_SSE_RECONNECTS) {
              window.setTimeout(connectSse, 1000);
              return;
            }
            startPolling();
          };
        };

        connectSse();
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "load failed");
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
      eventSource?.close();
      stopPolling();
    };
  }, [startPolling, stopPolling, taskId, refresh]);

  useEffect(() => {
    if (task && TERMINAL.includes(task.status)) {
      stopPolling();
      setConnectionMode("idle");
    }
  }, [task, stopPolling]);

  return { task, auditEvents, loading, error, connectionMode, refresh };
}
