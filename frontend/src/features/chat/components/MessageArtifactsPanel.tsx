import type { ChatArtifact } from '../artifactUtils'
import { ArtifactCardGrid } from './ArtifactCardGrid'

interface MessageArtifactsPanelProps {
  artifacts: ChatArtifact[]
  onOpenArtifact: (artifact: ChatArtifact) => void
}

export function MessageArtifactsPanel({
  artifacts,
  onOpenArtifact,
}: MessageArtifactsPanelProps) {
  if (artifacts.length === 0) return null

  return (
    <section className="mt-2.5 min-w-0 max-w-full space-y-2 overflow-hidden border-t border-[var(--color-border)] pt-2.5">
      <div className="text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
        Deliverables
      </div>
      <div className="w-fit min-w-0 max-w-[min(100%,30rem)]">
        <ArtifactCardGrid artifacts={artifacts} onOpenArtifact={onOpenArtifact} constrained />
      </div>
    </section>
  )
}
