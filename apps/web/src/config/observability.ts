/** Observability UI base URLs (override via Vite env). */
export const JAEGER_BASE_URL =
  import.meta.env.VITE_JAEGER_URL ?? "http://localhost:16686";

export const PROMETHEUS_BASE_URL =
  import.meta.env.VITE_PROMETHEUS_URL ?? "http://localhost:9090";

export function jaegerTraceUrl(traceId: string): string {
  return `${JAEGER_BASE_URL}/trace/${traceId}`;
}

export function prometheusExploreUrl(query: string): string {
  return `${PROMETHEUS_BASE_URL}/graph?g0.expr=${encodeURIComponent(query)}&g0.tab=0`;
}
