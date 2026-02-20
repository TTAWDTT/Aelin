import React from "react";
import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { listTrackings } from "../api/endpoints";
import type { TrackingItem } from "../api/types";
import { Button } from "../components/ui/Button";
import { Select } from "../components/ui/Select";
import { useLocalStorageState } from "../hooks/useLocalStorageState";

const WORKSPACES = [
  { key: "", label: "全部工作区" },
  { key: "default", label: "主工作区" },
  { key: "work", label: "工作" },
  { key: "life", label: "生活" },
  { key: "monitor", label: "监控" },
];

function TrackingRow({ item, onOpen }: { item: TrackingItem; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="focus-ring w-full rounded-xl border border-mist/70 bg-paper/70 p-3 text-left hover:border-stone/70"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs text-stone">
            {item.source} · {item.status} · {item.workspace}
          </div>
          <div className="mt-1 font-heading text-sm truncate">{item.target}</div>
          {item.query ? (
            <div className="mt-1 text-xs text-stone line-clamp-1">query: {item.query}</div>
          ) : null}
        </div>
        <div className="shrink-0">
          {item.unread_changes ? (
            <div className="rounded-full bg-accent-orange text-paper px-2 py-1 text-xs font-heading">
              {item.unread_changes}
            </div>
          ) : (
            <div className="text-xs text-stone">0</div>
          )}
        </div>
      </div>
    </button>
  );
}

export function TrackingPage() {
  const navigate = useNavigate();
  const [workspace, setWorkspace] = useLocalStorageState<string>("aelin:tracking:workspace:v1", "");
  const [status, setStatus] = useLocalStorageState<string>("aelin:tracking:status:v1", "");

  const { data, isLoading, error, mutate } = useSWR(
    ["tracking", workspace, status],
    () => listTrackings(workspace || undefined, status || undefined),
  );

  return (
    <div className="rounded-[var(--radius)] border border-mist/70 bg-paper/70 shadow-paper overflow-hidden">
      <header className="border-b border-mist/60 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-heading text-sm">Tracking</div>
            <div className="text-xs text-stone">长期跟踪中心：变化流与快照沉淀。</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => void mutate()}>
              刷新
            </Button>
          </div>
        </div>
      </header>

      <div className="p-4">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div>
            <div className="text-xs font-heading text-stone tracking-wide">Workspace</div>
            <div className="mt-2">
              <Select value={workspace} onChange={(e) => setWorkspace(e.target.value)}>
                {WORKSPACES.map((w) => (
                  <option key={w.key} value={w.key}>
                    {w.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div>
            <div className="text-xs font-heading text-stone tracking-wide">Status</div>
            <div className="mt-2">
              <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">全部</option>
                <option value="active">active</option>
                <option value="paused">paused</option>
                <option value="error">error</option>
              </Select>
            </div>
          </div>
          <div className="lg:col-span-1 flex items-end gap-2">
            <Button variant="subtle" onClick={() => navigate("/")}>
              去 Chat 创建跟踪
            </Button>
          </div>
        </div>

        <div className="mt-4">
          {isLoading ? (
            <div className="text-sm text-stone">加载中…</div>
          ) : error ? (
            <div className="text-sm text-stone">加载失败：{String((error as any)?.message || error)}</div>
          ) : (data?.items ?? []).length === 0 ? (
            <div className="text-sm text-stone">
              暂无跟踪目标。可在 Chat 中通过 “confirm_track” action 创建。
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {(data?.items ?? []).map((it) => (
                <TrackingRow
                  key={`${it.target_id ?? it.target}-${it.updated_at}`}
                  item={it}
                  onOpen={() => {
                    const tid = Number(it.target_id || 0);
                    if (tid) navigate(`/tracking/target/${tid}`);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

