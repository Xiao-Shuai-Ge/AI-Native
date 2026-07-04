import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
};

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch("/health");
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = (await response.json()) as HealthResponse;
        if (!cancelled) {
          setHealth(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "unknown error");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadHealth();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-16">
        <header className="space-y-2">
          <p className="text-sm uppercase tracking-[0.2em] text-slate-400">Day 1 Skeleton</p>
          <h1 className="text-4xl font-semibold">AI Native</h1>
          <p className="text-slate-300">多智能体协作平台 · 项目骨架已就绪</p>
        </header>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
          <h2 className="text-lg font-medium">API 健康检查</h2>
          {loading && <p className="mt-4 text-slate-400">加载中...</p>}
          {!loading && error && (
            <p className="mt-4 text-rose-300">无法连接 API：{error}</p>
          )}
          {!loading && !error && health && (
            <p className="mt-4 text-emerald-300">/health 返回：{health.status}</p>
          )}
        </section>
      </div>
    </main>
  );
}
