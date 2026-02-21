import { useEffect, type RefObject } from 'react'

export function useAutoScrollToBottom(
  scrollRef: RefObject<HTMLDivElement | null>,
  deps: readonly unknown[],
) {
  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    element.scrollTo({ top: element.scrollHeight, behavior: 'smooth' })
  }, deps)
}
