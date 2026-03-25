import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'

export function useAutoScrollToBottom(
  scrollRef: RefObject<HTMLDivElement | null>,
  deps: readonly unknown[],
  options?: {
    streaming?: boolean
    bottomThreshold?: number
  },
) {
  const { streaming = false, bottomThreshold = 72 } = options ?? {}
  const stickToBottomRef = useRef(true)
  const lastScrollHeightRef = useRef(0)

  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    const updateStickiness = () => {
      const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight
      stickToBottomRef.current = distanceFromBottom <= bottomThreshold
    }

    updateStickiness()
    element.addEventListener('scroll', updateStickiness, { passive: true })
    return () => element.removeEventListener('scroll', updateStickiness)
  }, [scrollRef, bottomThreshold])

  useLayoutEffect(() => {
    const element = scrollRef.current
    if (!element || !stickToBottomRef.current) return

    const nextScrollHeight = element.scrollHeight
    const behavior: ScrollBehavior =
      streaming || lastScrollHeightRef.current === 0 ? 'auto' : 'smooth'

    element.scrollTo({ top: nextScrollHeight, behavior })
    lastScrollHeightRef.current = nextScrollHeight
  }, [scrollRef, streaming, ...deps])
}
