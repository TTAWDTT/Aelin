import React from "react";
import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { listContacts } from "../api/endpoints";
import type { Contact } from "../api/types";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

function ContactRow({ contact, onOpen }: { contact: Contact; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="focus-ring w-full rounded-xl border border-mist/70 bg-paper/70 p-3 text-left hover:border-stone/70"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-heading text-sm truncate">{contact.display_name || "Unknown"}</div>
          <div className="mt-1 text-xs text-stone truncate">
            {contact.latest_preview || contact.handle}
          </div>
          <div className="mt-1 text-[11px] text-stone">
            {contact.latest_source ? `source: ${contact.latest_source}` : "source: —"}
          </div>
        </div>
        {contact.unread_count ? (
          <div className="shrink-0 rounded-full bg-accent-orange text-paper px-2 py-1 text-xs font-heading">
            {contact.unread_count}
          </div>
        ) : (
          <div className="shrink-0 text-xs text-stone">已读</div>
        )}
      </div>
    </button>
  );
}

export function SignalsPage() {
  const navigate = useNavigate();
  const [q, setQ] = React.useState("");
  const qd = useDebouncedValue(q, 250);

  const { data, isLoading, error, mutate } = useSWR(["contacts", qd], () => listContacts(qd));

  return (
    <div className="rounded-[var(--radius)] border border-mist/70 bg-paper/70 shadow-paper overflow-hidden">
      <header className="border-b border-mist/60 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-heading text-sm">Signals</div>
            <div className="text-xs text-stone">聚合信号，用于核验证据与处理未读。</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => void mutate()}>
              刷新
            </Button>
          </div>
        </div>
      </header>

      <div className="p-4">
        <div className="max-w-lg">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索联系人（姓名/handle）…" />
          <div className="mt-2 text-[11px] text-stone">点击联系人进入线程；在消息详情页可从 citation 跳转。</div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
          {isLoading ? (
            <div className="text-sm text-stone">加载中…</div>
          ) : error ? (
            <div className="text-sm text-stone">加载失败：{String((error as any)?.message || error)}</div>
          ) : (data ?? []).length === 0 ? (
            <div className="text-sm text-stone">暂无联系人。先在 Settings 连接数据源并同步。</div>
          ) : (
            (data ?? []).map((c) => (
              <ContactRow key={c.id} contact={c} onOpen={() => navigate(`/signals/contact/${c.id}`)} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

