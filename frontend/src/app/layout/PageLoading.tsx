export function PageLoading() {
  return (
    <div className="min-h-dvh grid place-items-center px-6">
      <div className="max-w-sm w-full rounded-[var(--radius)] border border-mist/70 bg-paper/70 shadow-paper p-5">
        <div className="text-sm text-stone font-heading tracking-wide">Aelin</div>
        <div className="mt-2 h-2 w-40 rounded-full bg-mist/70 overflow-hidden">
          <div className="h-full w-2/3 animate-pulse bg-accent-blue/70" />
        </div>
        <div className="mt-3 text-xs text-stone">加载中…</div>
      </div>
    </div>
  );
}

