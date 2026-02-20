import { useState, useEffect } from 'react'

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const cb = (e: MediaQueryListEvent) => setMatches(e.matches)
    mq.addEventListener('change', cb)
    setMatches(mq.matches)
    return () => mq.removeEventListener('change', cb)
  }, [query])
  return matches
}
