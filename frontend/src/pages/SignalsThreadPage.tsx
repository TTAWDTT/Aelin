import React from "react";
import useSWR from "swr";
import { useNavigate, useParams } from "react-router-dom";
import { listContactMessages, markContactRead } from "../api/endpoints";
import type { MessageOut } from "../api/types";
import { Button } from "../components/ui/Button";
import { useToast } from "../app/providers/ToastProvider";

function MessageCard({ msg, onOpen }: { msg: MessageOut; onOpen: () => void }) {
  return (
    <button
      type="button"
      className="focus-ring w-full rounded-xl border border-mist/70 bg-paper/70 p-3 text-left hover:border-stone/70"
      onClick={onOpen}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs text-stone">{msg.source}</div>
          <div className="mt-1 font-heading text-sm truncate">{msg.subject || msg.sender}</div>
          <div className="mt-1 text-xs text-stone line-clamp-2">{msg.body_preview}</div>
        </div>
        <div className="shrink-0 text-xs text-stone">{msg.is_read ? "已读" : "未读"}</div>
      </div>
    </button>
  );
}

export function SignalsThreadPage() {
  const params = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const contactId = Number(params.contactId || 0);

  const { data, isLoading, error, mutate } = useSWR(
    contactId ? ["contact-messages", contactId] : null,
    () => listContactMessages(contactId),
  );

  const markRead = async () => {
    if (!contactId) return;
    try {
      const res = await markContactRead(contactId);
      showToast(`已标记已读：${res.marked} 条`, "success");
      void mutate();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "标记失败", "error");
    }
  };

  return (
    <div className="rounded-[var(--radius)] border border-mist/70 bg-paper/70 shadow-paper overflow-hidden">
      <header className="border-b border-mist/60 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-heading text-sm">Thread</div>
            <div className="text-xs text-stone">contact_id={contactId || "—"}</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => navigate("/signals")}>
              返回
            </Button>
            <Button variant="subtle" onClick={() => void mutate()}>
              刷新
            </Button>
            <Button tone="green" onClick={() => void markRead()}>
              标记已读
            </Button>
          </div>
        </div>
      </header>

      <div className="p-4">
        {isLoading ? (
          <div className="text-sm text-stone">加载中…</div>
        ) : error ? (
          <div className="text-sm text-stone">
            加载失败：{String((error as any)?.message || error)}
          </div>
        ) : (data ?? []).length === 0 ? (
          <div className="text-sm text-stone">暂无消息。</div>
        ) : (
          <div className="space-y-3">
            {(data ?? []).map((m) => (
              <MessageCard key={m.id} msg={m} onOpen={() => navigate(`/message/${m.id}`)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

