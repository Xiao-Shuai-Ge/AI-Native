import { apiFetch } from "./client";
import type { ToolListResponse } from "./types";

export async function listTools(): Promise<ToolListResponse> {
  return apiFetch<ToolListResponse>("/api/tools");
}
