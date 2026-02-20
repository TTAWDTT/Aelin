import useSWR from "swr";
import { useNavigate, useParams } from "react-router-dom";
import { getMessage } from "../api/endpoints";
import { Button } from "../components/ui/Button";

export function MessagePage() {
  const params = useParams();
  const navigate = useNavigate();
  const messageId = Number(params.messageId || 0);

  const { data, isLoading, error } = useSWR(
    messageId ? ["message", messageId] : null,
    () => getMessage(messageId),
  );

  return (
    <div className="rounded-[var(--radius)] border border-mist/70 bg-paper/70 shadow-paper overflow-hidden">
      <header className="border-b border-mist/60 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-heading text-sm">Message</div>
            <div className="text-xs text-stone">message_id={messageId || "—"}</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => navigate(-1)}>
              返回
            </Button>
            {data?.contact_id ? (
              <Button variant="subtle" onClick={() => navigate(`/signals/contact/${data.contact_id}`)}>
                打开线程
              </Button>
            ) : null}
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
        ) : !data ? (
          <div className="text-sm text-stone">未找到消息。</div>
        ) : (
          <div className="space-y-3">
            <div className="rounded-xl border border-mist/70 bg-paper/70 p-3">
              <div className="text-xs text-stone">{data.source}</div>
              <div className="mt-1 font-heading text-lg leading-snug">{data.subject || data.sender}</div>
              <div className="mt-1 text-xs text-stone">{data.sender}</div>
            </div>
            <div className="rounded-xl border border-mist/70 bg-paper/70 p-3">
              <div className="text-xs font-heading text-stone tracking-wide">Body</div>
              <div className="mt-2 whitespace-pre-wrap leading-relaxed text-sm">{data.body}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

