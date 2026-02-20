import React from "react";

type Mode = "light" | "dark";
const THEME_KEY = "aelin:theme:v1";

function readInitialMode(): Mode {
  try {
    const raw = (localStorage.getItem(THEME_KEY) || "").trim().toLowerCase();
    if (raw === "light" || raw === "dark") return raw;
  } catch {
    // ignore
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
}

function applyMode(mode: Mode) {
  document.documentElement.dataset.theme = mode;
}

const ThemeContext = React.createContext<{
  mode: Mode;
  setMode: (mode: Mode) => void;
  toggle: () => void;
} | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = React.useState<Mode>(() => readInitialMode());

  const setMode = React.useCallback((next: Mode) => {
    setModeState(next);
    applyMode(next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // ignore
    }
  }, []);

  const toggle = React.useCallback(() => {
    setMode(mode === "dark" ? "light" : "dark");
  }, [mode, setMode]);

  React.useEffect(() => {
    applyMode(mode);
  }, [mode]);

  return (
    <ThemeContext.Provider value={{ mode, setMode, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useThemeMode() {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("ThemeProvider missing");
  return ctx;
}

