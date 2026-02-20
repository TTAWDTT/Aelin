export function isNativeMobileShell(): boolean {
  // Kept intentionally simple; we can reintroduce Capacitor runtime probing later.
  return Boolean((window as any)?.Capacitor?.isNativePlatform?.());
}

