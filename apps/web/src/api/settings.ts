import { apiFetch } from "./client";
import type { RuntimeSettings } from "./types";

export async function getSettings(): Promise<RuntimeSettings> {
  return apiFetch<RuntimeSettings>("/api/settings");
}

export async function updateSettings(settings: Partial<RuntimeSettings>): Promise<RuntimeSettings> {
  return apiFetch<RuntimeSettings>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}
