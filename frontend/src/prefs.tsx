// Language and theme: kept per device in the browser (decision 2026-10-30).

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { plurals, strings } from "./i18n";
import { plural } from "./lib/text";
import type { Lang } from "./lib/text";

export type ThemeChoice = "light" | "dark" | "system";

interface Prefs {
  lang: Lang;
  L: (typeof strings)[Lang];
  count: (key: keyof typeof plurals, n: number) => string;
  setLang: (lang: Lang) => void;
  themeChoice: ThemeChoice;
  theme: "light" | "dark";
  setTheme: (theme: ThemeChoice) => void;
}

const Context = createContext<Prefs | null>(null);

function stored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // private window: the choice lasts until the page closes
  }
}

const systemTheme = () =>
  matchMedia("(prefers-color-scheme: light)").matches ? ("light" as const) : ("dark" as const);

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(stored("sabq.lang") === "fr" ? "fr" : "ar");
  const [themeChoice, setThemeChoice] = useState<ThemeChoice>(
    () => (stored("sabq.theme") as ThemeChoice | null) ?? "system",
  );
  const [system, setSystem] = useState(systemTheme);

  useEffect(() => {
    const query = matchMedia("(prefers-color-scheme: light)");
    const update = () => setSystem(systemTheme());
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  const theme = themeChoice === "system" ? system : themeChoice;

  useEffect(() => {
    const root = document.documentElement;
    root.lang = lang;
    root.dir = lang === "ar" ? "rtl" : "ltr";
    root.dataset.theme = theme;
    document.title = strings[lang].brand;
  }, [lang, theme]);

  const setLang = useCallback((next: Lang) => {
    store("sabq.lang", next);
    setLangState(next);
  }, []);

  const setTheme = useCallback((next: ThemeChoice) => {
    store("sabq.theme", next);
    setThemeChoice(next);
  }, []);

  const value = useMemo<Prefs>(
    () => ({
      lang,
      L: strings[lang],
      count: (key, n) => plural(lang, n, plurals[key][lang]),
      setLang,
      themeChoice,
      theme,
      setTheme,
    }),
    [lang, setLang, themeChoice, theme, setTheme],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function usePrefs(): Prefs {
  const prefs = useContext(Context);
  if (!prefs) throw new Error("usePrefs outside PrefsProvider");
  return prefs;
}
