import { NavLink, Outlet } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-2 text-sm font-medium ${
    isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
  }`;

export function Layout() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/80">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500">AI Native</p>
            <h1 className="text-xl font-semibold">多智能体协作控制台</h1>
          </div>
          <nav className="flex gap-2">
            <NavLink to="/" className={linkClass} end>
              新建任务
            </NavLink>
            <NavLink to="/history" className={linkClass}>
              历史与设置
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
