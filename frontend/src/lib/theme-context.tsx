"use client";

import { createContext, useContext, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "buddy-theme";

interface ThemeContextValue {
  theme: Theme;
  /** False until the client has read the real theme off <html> (set by
   * the inline script in layout.tsx before hydration) — lets consumers
   * avoid rendering a theme-dependent icon that would flash/mismatch
   * between the SSR default and the actual stored preference. */
  mounted: boolean;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Private browsing / blocked storage — theme still applies for this
    // page load via the DOM attribute, it just won't persist.
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Matches the server-rendered default exactly (no data-theme attribute
  // yet) so the first client render can't mismatch it — the real value,
  // already set on <html> by the inline script below, is read in the
  // effect below instead.
  const [theme, setThemeState] = useState<Theme>("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // Reading the DOM attribute the inline script already set — a
    // synchronous external-system read, nothing async to defer this
    // into (mirrors SceneTransition.tsx's own use of this escape hatch).
    const current = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setThemeState(current);
    setMounted(true);
  }, []);

  function setTheme(next: Theme) {
    setThemeState(next);
    applyTheme(next);
  }

  function toggleTheme() {
    setTheme(theme === "dark" ? "light" : "dark");
  }

  return (
    <ThemeContext.Provider value={{ theme, mounted, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}

/** Inline, render-blocking script — sets data-theme on <html> before the
 * page paints, so there's no flash of the wrong theme while React
 * hydrates. Reads localStorage first, then falls back to the OS
 * preference for a first-ever visit (after that, the explicit choice in
 * localStorage always wins over the OS). */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('${STORAGE_KEY}');if(t!=='light'&&t!=='dark'){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}document.documentElement.setAttribute('data-theme',t);}catch(e){}})();`;
