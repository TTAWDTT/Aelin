import { useEffect, type RefObject } from 'react'

export function useAutoScrollToBottom(
  scrollRef: RefObject<HTMLDivElement | null>,
  deps: readonly unknown[],
  behavior: ScrollBehavior = 'smooth',
) {
  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight
    const shouldStickToBottom = distanceFromBottom <= 120 || element.scrollTop === 0
    if (!shouldStickToBottom) return
    element.scrollTo({ top: element.scrollHeight, behavior })
  }, deps)
}
