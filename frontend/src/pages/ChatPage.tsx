import React from "react";
import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { aelinChatStream, aelinConfirmTrack, getAelinContext } from "../api/endpoints";
import type {
  AelinAction,
  AelinChatResponse,
  AelinCitation,
  AelinToolStep,
} from "../api/types";
import { Markdown } from "../components/Markdown";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { useToast } from "../app/providers/ToastProvider";

type EvidenceItem = {
  citation: AelinCitation;
  snippet?: string;
  provider?: string;
  fetch_mode?: string;
};

type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  status?: "thinking" | "done" | "error";
  result?: AelinChatResponse;
  trace?: AelinToolStep[];
  evidence?: EvidenceItem[];
};

function newId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const WORKSPACES = [
  { key: "default", label: "主工作区" },
  { key: "work", label: "工作" },
  { key: "life", label: "生活" },
  { key: "monitor", label: "监控" },
];

function normalizeHistory(turns: ChatTurn[]) {
  const out: { role: "user" | "assistant"; content: string }[] = [];
  for (const t of turns.slice(-12)) {
    const content = String(t.content || "").trim();
    if (!content) continue;
    out.push({ role: t.role, content: content.slice(0, 3000) });
  }
  return out;
}

function mergeTrace(prev: AelinToolStep[] | undefined, step: AelinToolStep): AelinToolStep[] {
  const next = [...(prev ?? [])];
  const idx = next.findIndex((it) => it.stage === step.stage);
  if (idx === -1) next.push(step);
  else next[idx] = { ...next[idx], ...step };
  return next;
}

export function ChatPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [workspace, setWorkspace] = useLocalStorageState<string>("aelin:workspace:v1", "default");
  const [searchMode, setSearchMode] = useLocalStorageState<string>("aelin:search-mode:v1", "auto");
  const [draft, setDraft] = React.useState("");
  const debouncedDraft = useDebouncedValue(draft, 120);
  const [turns, setTurns] = useLocalStorageState<ChatTurn[]>(
    `aelin:chat:turns:${workspace}:v1`,
    [],
  );
  const [busy, setBusy] = React.useState(false);
  const [activeEvidence, setActiveEvidence] = React.useState<EvidenceItem[]>([]);
  const [activeTrace, setActiveTrace] = React.useState<AelinToolStep[]>([]);
  const abortRef = React.useRef<AbortController | null>(null);

  const { data: context, mutate: mutateContext, isLoading: contextLoading } = useSWR(
    ["aelin-context", workspace],
    () => getAelinContext(workspace),
  );

  const send = React.useCallback(async () => {
    const query = draft.trim();
    if (!query || busy) return;

    const userTurn: ChatTurn = {
      id: newId("u"),
      role: "user",
      content: query,
      createdAt: Date.now(),
      status: "done",
    };
    const assistantTurnId = newId("a");
    const assistantTurn: ChatTurn = {
      id: assistantTurnId,
      role: "assistant",
      content: "生成中…",
      createdAt: Date.now(),
      status: "thinking",
      trace: [],
      evidence: [],
    };

    setBusy(true);
    setDraft("");
    setActiveEvidence([]);
    setActiveTrace([]);
    setTurns((prev) => [...prev, userTurn, assistantTurn]);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const history = normalizeHistory([...turns, userTurn]);

    try {
      await aelinChatStream(
        {
          query,
          workspace,
          use_memory: true,
          max_citations: 8,
          history,
          search_mode: searchMode,
        },
        (evt) => {
          if (evt.event === "trace" && evt.data?.step) {
            const step = evt.data.step as AelinToolStep;
            setActiveTrace((prev) => mergeTrace(prev, step));
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurnId ? { ...t, trace: mergeTrace(t.trace, step) } : t,
              ),
            );
          }
          if (evt.event === "evidence" && evt.data?.citation) {
            const item: EvidenceItem = {
              citation: evt.data.citation as AelinCitation,
              snippet: String(evt.data.snippet || ""),
              provider: String(evt.data.provider || ""),
              fetch_mode: String(evt.data.fetch_mode || ""),
            };
            setActiveEvidence((prev) => [...prev, item].slice(0, 12));
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurnId
                  ? { ...t, evidence: [...(t.evidence ?? []), item].slice(0, 12) }
                  : t,
              ),
            );
          }
          if (evt.event === "final" && evt.data?.result) {
            const result = evt.data.result as AelinChatResponse;
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurnId
                  ? { ...t, status: "done", result, content: result.answer }
                  : t,
              ),
            );
            void mutateContext();
          }
          if (evt.event === "error") {
            const message = String(evt.data?.message || "stream error");
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurnId ? { ...t, status: "error", content: message } : t,
              ),
            );
          }
        },
        controller.signal,
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : "请求失败";
      showToast(msg, "error");
      setTurns((prev) =>
        prev.map((t) =>
          t.id === assistantTurnId ? { ...t, status: "error", content: msg } : t,
        ),
      );
    } finally {
      setBusy(false);
    }
  }, [busy, draft, mutateContext, searchMode, setDraft, setTurns, showToast, turns, workspace]);

  const latestAssistant = [...turns].reverse().find((t) => t.role === "assistant");
  const actions = latestAssistant?.result?.actions ?? [];
  const citations = latestAssistant?.result?.citations ?? [];

  const handleAction = React.useCallback(
    async (action: AelinAction) => {
      const kind = String(action.kind || "");
      const payload = action.payload || {};
      if (kind === "open_message") {
        const messageId = Number(payload.message_id || 0);
        if (messageId) navigate(`/message/${messageId}`);
        return;
      }
      if (kind === "open_desk") {
        navigate("/signals");
        return;
      }
      if (kind === "open_settings") {
        navigate("/settings");
        return;
      }
      if (kind === "open_tracking") {
        const targetId = Number(payload.target_id || payload.targetId || 0);
        if (targetId) navigate(`/tracking/target/${targetId}`);
        else navigate("/tracking");
        return;
      }
      if (kind === "confirm_track") {
        const target = String(payload.target || "").trim();
        if (!target) return;
        showToast("创建跟踪中…", "info");
        try {
          const res = await aelinConfirmTrack({
            target,
            source: String(payload.source || "auto"),
            query: String(payload.query || latestAssistant?.content || ""),
            workspace,
          });
          const status = String(res?.status || "");
          const message = String(res?.message || "已提交");
          showToast(
            `${status}: ${message}`,
            status === "needs_config" ? "error" : "success",
          );
          if (status === "needs_config") navigate("/settings");
          if (status === "tracking_enabled" && res?.target_id)
            navigate(`/tracking/target/${Number(res.target_id)}`);
        } catch (e) {
          showToast(e instanceof Error ? e.message : "跟踪创建失败", "error");
        }
        return;
      }
      showToast(`未实现的 action：${kind}`, "info");
    },
    [latestAssistant?.content, navigate, showToast, workspace],
  );

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="rounded-[var(--radius)] border border-mist/70 bg-paper/70 shadow-paper overflow-hidden">
        <header className="border-b border-mist/60 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-[220px]">
              <div className="font-heading text-sm">Chat</div>
              <div className="text-xs text-stone">
                答案优先，证据可查，动作可执行。
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="w-[140px]">
                <Select
                  value={workspace}
                  onChange={(e) => setWorkspace(e.target.value)}
                >
                  {WORKSPACES.map((w) => (
                    <option key={w.key} value={w.key}>
                      {w.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="w-[120px]">
                <Select
                  value={searchMode}
                  onChange={(e) => setSearchMode(e.target.value)}
                >
                  <option value="auto">Auto</option>
                  <option value="local">Local</option>
                  <option value="web">Web</option>
                </Select>
              </div>
              <Button
                variant="ghost"
                onClick={() => {
                  setTurns([]);
                  showToast("已清空会话", "info");
                }}
              >
                清空
              </Button>
            </div>
          </div>
        </header>

        <div className="px-4 py-4">
          <div className="space-y-3">
            {turns.length === 0 ? (
              <div className="rounded-xl border border-mist/70 bg-paper/70 p-4">
                <div className="font-heading text-sm">快速开始</div>
                <div className="mt-2 text-sm text-stone leading-relaxed">
                  试试问一个你关心的持续主题，比如：某个账号最近有什么新动态、某个项目的最新进展、或者“今天有哪些值得我跟进的更新？”。
                </div>
              </div>
            ) : null}

            {turns.map((t) => (
              <div
                key={t.id}
                className={t.role === "user" ? "flex justify-end" : "flex justify-start"}
              >
                <div
                  className={
                    t.role === "user"
                      ? "max-w-[860px] rounded-2xl bg-ink text-paper px-4 py-3"
                      : "max-w-[860px] rounded-2xl border border-mist/70 bg-paper/70 px-4 py-3"
                  }
                >
                  <div className="text-xs text-stone/90 font-heading tracking-wide">
                    {t.role === "user"
                      ? "YOU"
                      : t.status === "thinking"
                        ? "AELIN · WORKING"
                        : "AELIN"}
                    {t.result?.expression ? (
                      <span className="ml-2 inline-flex items-center rounded-md border border-mist/70 bg-paper/60 px-2 py-0.5 text-[11px] text-ink">
                        {t.result.expression}
                      </span>
                    ) : null}
                  </div>
                  <div
                    className={
                      t.role === "user"
                        ? "mt-2 whitespace-pre-wrap leading-relaxed"
                        : "mt-2 prose prose-sm max-w-none prose-p:leading-relaxed prose-headings:font-heading prose-a:text-ink"
                    }
                  >
                    {t.role === "assistant" ? <Markdown>{t.content}</Markdown> : t.content}
                  </div>

                  {t.role === "assistant" && t.result?.citations?.length ? (
                    <div className="mt-3 border-t border-mist/60 pt-3">
                      <div className="text-xs font-heading text-stone tracking-wide">
                        Citations
                      </div>
                      <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                        {t.result.citations.slice(0, 6).map((c) => (
                          <button
                            key={`${c.message_id}-${c.title}`}
                            type="button"
                            className="focus-ring rounded-xl border border-mist/70 bg-paper/70 px-3 py-2 text-left hover:border-stone/70"
                            onClick={() => navigate(`/message/${c.message_id}`)}
                          >
                            <div className="text-xs text-stone">{c.source_label}</div>
                            <div className="mt-1 text-sm font-heading line-clamp-2">
                              {c.title}
                            </div>
                            <div className="mt-1 text-xs text-stone line-clamp-1">
                              {c.sender}
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {t.role === "assistant" && t.result?.actions?.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {t.result.actions.map((a) => (
                        <button
                          key={`${a.kind}-${a.title}`}
                          type="button"
                          className="focus-ring rounded-full border border-mist/70 bg-paper/70 px-3 py-1.5 text-sm hover:border-stone/70"
                          onClick={() => void handleAction(a)}
                        >
                          <span className="font-heading">{a.title}</span>
                          {a.detail ? (
                            <span className="ml-2 text-xs text-stone">{a.detail}</span>
                          ) : null}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>

        <footer className="border-t border-mist/60 p-3">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Input
                value={draft}
                placeholder="问一个你想长期弄清楚的问题…"
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    void send();
                  }
                }}
              />
              <div className="mt-2 text-[11px] text-stone">
                Ctrl/⌘ + Enter 发送 · workspace={workspace} · mode={searchMode}
                {debouncedDraft.trim() ? "" : ""}
              </div>
            </div>
            <Button tone="orange" disabled={!draft.trim() || busy} onClick={() => void send()}>
              发送
            </Button>
          </div>
        </footer>
      </section>

      <aside className="rounded-[var(--radius)] border border-mist/70 bg-paper/60 shadow-paper overflow-hidden">
        <div className="border-b border-mist/60 px-4 py-3">
          <div className="font-heading text-sm">Context</div>
          <div className="text-xs text-stone">记忆摘要 · 今日焦点 · 证据进度</div>
        </div>

        <div className="px-4 py-4 space-y-4">
          <div>
            <div className="flex items-center justify-between">
              <div className="text-xs font-heading text-stone tracking-wide">
                Memory Summary
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void mutateContext()}
                disabled={contextLoading}
              >
                刷新
              </Button>
            </div>
            <div className="mt-2 rounded-xl border border-mist/70 bg-paper/70 p-3 text-sm leading-relaxed">
              {context?.summary?.trim() ? (
                <Markdown>{context.summary}</Markdown>
              ) : (
                <span className="text-stone">暂无摘要（先同步一些信号）。</span>
              )}
            </div>
          </div>

          <div>
            <div className="text-xs font-heading text-stone tracking-wide">
              Live Trace
            </div>
            <div className="mt-2 space-y-2">
              {(latestAssistant?.status === "thinking"
                ? activeTrace
                : latestAssistant?.trace ?? []
              )
                .slice(-7)
                .map((s) => (
                  <div
                    key={s.stage}
                    className="rounded-xl border border-mist/70 bg-paper/70 p-3"
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-heading text-sm">{s.stage}</div>
                      <div className="text-xs text-stone">{s.status}</div>
                    </div>
                    {s.detail ? (
                      <div className="mt-1 text-xs text-stone leading-relaxed">
                        {s.detail}
                      </div>
                    ) : null}
                  </div>
                ))}
              {(latestAssistant?.status === "thinking"
                ? activeTrace
                : latestAssistant?.trace ?? []
              ).length === 0 ? (
                <div className="text-sm text-stone">等待工具轨迹…</div>
              ) : null}
            </div>
          </div>

          <div>
            <div className="text-xs font-heading text-stone tracking-wide">
              Evidence Feed
            </div>
            <div className="mt-2 space-y-2">
              {(latestAssistant?.status === "thinking"
                ? activeEvidence
                : latestAssistant?.evidence ?? []
              )
                .slice(0, 6)
                .map((ev) => (
                  <button
                    key={`${ev.citation.message_id}-${ev.citation.title}`}
                    type="button"
                    className="focus-ring w-full rounded-xl border border-mist/70 bg-paper/70 p-3 text-left hover:border-stone/70"
                    onClick={() => navigate(`/message/${ev.citation.message_id}`)}
                  >
                    <div className="text-xs text-stone">
                      {ev.citation.source_label} · {ev.provider || "source"}
                    </div>
                    <div className="mt-1 font-heading text-sm line-clamp-2">
                      {ev.citation.title}
                    </div>
                    {ev.snippet ? (
                      <div className="mt-1 text-xs text-stone line-clamp-3">
                        {ev.snippet}
                      </div>
                    ) : null}
                  </button>
                ))}
              {(latestAssistant?.status === "thinking"
                ? activeEvidence
                : latestAssistant?.evidence ?? []
              ).length === 0 ? (
                <div className="text-sm text-stone">
                  暂无证据事件（可能本次无需检索）。
                </div>
              ) : null}
            </div>
          </div>

          <div>
            <div className="text-xs font-heading text-stone tracking-wide">
              Quick Open
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button variant="subtle" size="sm" onClick={() => navigate("/signals")}>
                打开 Signals
              </Button>
              <Button variant="subtle" size="sm" onClick={() => navigate("/tracking")}>
                打开 Tracking
              </Button>
              <Button variant="subtle" size="sm" onClick={() => navigate("/settings")}>
                打开 Settings
              </Button>
            </div>
          </div>

          <div>
            <div className="text-xs font-heading text-stone tracking-wide">
              Citations
            </div>
            <div className="mt-2 text-sm text-stone">
              {citations.length ? `${citations.length} 条` : "暂无"}
            </div>
            {citations.slice(0, 3).map((c) => (
              <button
                key={`ctx-cite-${c.message_id}-${c.title}`}
                type="button"
                className="focus-ring mt-2 w-full rounded-xl border border-mist/70 bg-paper/70 p-3 text-left hover:border-stone/70"
                onClick={() => navigate(`/message/${c.message_id}`)}
              >
                <div className="text-xs text-stone">{c.source_label}</div>
                <div className="mt-1 font-heading text-sm line-clamp-2">{c.title}</div>
              </button>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}

