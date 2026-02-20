import React from "react";
import useSWR from "swr";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson, postJson } from "../api/client";
import { Button } from "../components/ui/Button";
import { Select } from "../components/ui/Select";

type ChangeItem = {
  id: number;
  target_id: number;
  change_type: string;
  severity: string;
  title: string;
  detail: string;
  acked: boolean;
  created_at: string;
};

type ChangesResponse = { total: number; items: ChangeItem[]; generated_at: string };

export function TrackingTargetPage() {
  const params = useParams();
  const navigate = useNavigate();
  const targetId = Number(params.targetId || 0);

  const [severity, setSeverity] = React.useState("");
  const [acked, setAcked] = React.useState<string>("false");

  const { data, isLoading, error, mutate } = useSWR(
    targetId ? ["tracking-changes", targetId, severity, acked] : null,
    async () => {
      const qs = new URLSearchParams();
      qs.set("limit", "120");
      if (severity) qs.set("severity", severity);
      if (acked === "true") qs.set("acked", "true");
      if (acked === "false") qs.set("acked", "false");
      return fetchJson<ChangesResponse>(
        `/api/v1/aelin/tracking/targets/${targetId}/changes?${qs.toString()}`,
      );
    },
  );

  const ackChange = async (id: number) => {
    await postJson(`/api/v1/aelin/tracking/changes/${id}/ack`, {});
    void mutate();
  };

  return (
    <div className="rounded-[var(--radius)] border border-mist/70 bg-paper/70 shadow-paper overflow-hidden">
      <header className="border-b border-mist/60 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-heading text-sm">Tracking Detail</div>
            <div className="text-xs text-stone">target_id={targetId || "—"} · changes</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => navigate("/tracking")}>返回</Button>
            <Button variant="subtle" onClick={() => void mutate()}>刷新</Button>
          </div>
        </div>
      </header>

      <div className="p-4">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div>
            <div className="text-xs font-heading text-stone tracking-wide">Severity</div>
            <div className="mt-2">
              <Select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                <option value="">全部</option>
                <option value="critical">critical</option>
                <option value="high">high</option>
                <option value="medium">medium</option>
                <option value="low">low</option>
              </Select>
            </div>
          </div>
          <div>
            <div className="text-xs font-heading text-stone tracking-wide">Acked</div>
            <div className="mt-2">
              <Select value={acked} onChange={(e) => setAcked(e.target.value)}>
                <option value="">全部</option>
                <option value="false">未确认</option>
                <option value="true">已确认</option>
              </Select>
            </div>
          </div>
          <div className="flex items-end gap-2">
            <Button variant="subtle" onClick={() => navigate("/")}>去 Chat 追问</Button>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {isLoading ? (
            <div className="text-sm text-stone">加载中…</div>
          ) : error ? (
            <div className="text-sm text-stone">加载失败：{String((error as any)?.message || error)}</div>
          ) : (data?.items ?? []).length === 0 ? (
            <div className="text-sm text-stone">暂无变化记录。</div>
          ) : (
            (data?.items ?? []).map((c) => (
              <div key={c.id} className="rounded-xl border border-mist/70 bg-paper/70 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-xs text-stone">{c.severity} · {c.change_type}</div>
                    <div className="mt-1 font-heading text-sm">{c.title}</div>
                    {c.detail ? (
                      <div className="mt-1 text-xs text-stone leading-relaxed whitespace-pre-wrap">
                        {c.detail}
                      </div>
                    ) : null}
                    <div className="mt-2 text-[11px] text-stone">{c.created_at}</div>
                  </div>
                  <div className="shrink-0">
                    {c.acked ? (
                      <div className="text-xs text-stone">已确认</div>
                    ) : (
                      <Button size="sm" tone="green" onClick={() => void ackChange(c.id)}>
                        确认
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

