import { useEffect, useState } from 'react'

const DEFAULT_WIDTH = 1024

export function useViewportWidth() {
  const [width, setWidth] = useState(() => (typeof window === 'undefined' ? DEFAULT_WIDTH : window.innerWidth))

  useEffect(() => {
    const handleResize = () => setWidth(window.innerWidth)
    window.addEventListener('resize', handleResize, { passive: true })
    handleResize()
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  return width
}
