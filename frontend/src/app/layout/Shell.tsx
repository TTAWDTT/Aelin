import { Outlet, useLocation, useNavigate } from "react-router-dom";
import clsx from "clsx";
import { useThemeMode } from "../providers/ThemeProvider";
import { useToast } from "../providers/ToastProvider";

const NAV = [
  { key: "chat", label: "Chat", path: "/", hint: "Evidence-first 对话" },
  { key: "signals", label: "Signals", path: "/signals", hint: "聚合与核验" },
  { key: "tracking", label: "Tracking", path: "/tracking", hint: "长期跟踪" },
  { key: "settings", label: "Settings", path: "/settings", hint: "配置与健康" },
] as const;

export function Shell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { mode, toggle } = useThemeMode();
  const { showToast } = useToast();

  const activeKey =
    NAV.find((it) =>
      it.path === "/"
        ? location.pathname === "/"
        : location.pathname === it.path || location.pathname.startsWith(`${it.path}/`),
    )?.key ?? "chat";

  return (
    <div className="min-h-dvh">
      <div className="mx-auto max-w-[1280px] px-4 py-4 lg:py-6">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
          <aside className="lg:sticky lg:top-6">
            <div className="rounded-[var(--radius)] border border-mist/70 bg-paper/70 shadow-paper overflow-hidden">
              <div className="px-4 py-4 border-b border-mist/60">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-heading text-base tracking-tight">Aelin</div>
                    <div className="text-xs text-stone">Editorial Evidence Desk</div>
                  </div>
                  <button
                    type="button"
                    className="focus-ring rounded-md border border-mist/70 bg-paper px-2 py-1 text-xs text-stone hover:border-stone/60"
                    onClick={() => {
                      toggle();
                      showToast(mode === "dark" ? "切换到浅色" : "切换到深色", "info");
                    }}
                  >
                    {mode === "dark" ? "Light" : "Dark"}
                  </button>
                </div>
              </div>

              <nav className="p-2">
                {NAV.map((item) => {
                  const active = item.key === activeKey;
                  return (
                    <button
                      key={item.key}
                      type="button"
                      className={clsx(
                        "focus-ring w-full text-left rounded-lg px-3 py-2.5 transition",
                        active
                          ? "bg-ink text-paper shadow-sm"
                          : "hover:bg-mist/60 text-ink",
                      )}
                      onClick={() => navigate(item.path)}
                    >
                      <div className={clsx("font-heading text-sm tracking-tight", active && "text-paper")}>
                        {item.label}
                      </div>
                      <div className={clsx("text-xs", active ? "text-paper/75" : "text-stone")}>
                        {item.hint}
                      </div>
                    </button>
                  );
                })}
              </nav>

              <div className="px-4 pb-4 pt-2 text-[11px] text-stone">
                <div className="flex items-center justify-between">
                  <span>API</span>
                  <a className="focus-ring underline decoration-stone/40 hover:decoration-stone" href="/api/v1" target="_blank" rel="noreferrer">
                    /api/v1
                  </a>
                </div>
              </div>
            </div>

            <div className="mt-4 hidden lg:block rounded-[var(--radius)] border border-mist/70 bg-paper/60 p-4">
              <div className="font-heading text-xs tracking-wide text-stone">Tip</div>
              <div className="mt-2 text-sm leading-relaxed">
                在 Chat 里点击证据卡，可一键跳到 Signals 核验上下文，然后用 Tracking 让主题持续更新。
              </div>
            </div>
          </aside>

          <main className="min-w-0">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
