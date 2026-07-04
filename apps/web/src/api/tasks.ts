import { apiFetch } from "./client";
import type {
  CreateTaskResponse,
  EngineChoice,
  TaskControlResponse,
  TaskDetail,
  TaskSummary,
} from "./types";

export type CreateTaskInput = {
  user_query: string;
  engine: EngineChoice;
  user_id?: string;
};

export async function createTask(input: CreateTaskInput): Promise<CreateTaskResponse> {
  return apiFetch<CreateTaskResponse>("/api/tasks", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function listTasks(): Promise<TaskSummary[]> {
  return apiFetch<TaskSummary[]>("/api/tasks");
}

export async function getTask(taskId: string): Promise<TaskDetail> {
  return apiFetch<TaskDetail>(`/api/tasks/${taskId}`);
}

export async function pauseTask(taskId: string): Promise<TaskControlResponse> {
  return apiFetch<TaskControlResponse>(`/api/tasks/${taskId}/pause`, { method: "POST" });
}

export async function resumeTask(taskId: string): Promise<TaskControlResponse> {
  return apiFetch<TaskControlResponse>(`/api/tasks/${taskId}/resume`, { method: "POST" });
}

export function taskEventsUrl(taskId: string): string {
  return `/api/tasks/${taskId}/events`;
}
