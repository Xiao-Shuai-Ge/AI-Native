import { apiFetch } from "./client";
import type { LLMProviderInfo } from "./types";

export async function getProviders(): Promise<LLMProviderInfo> {
  return apiFetch<LLMProviderInfo>("/api/providers");
}
