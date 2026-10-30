// Filters and search live in the URL: they survive a reload and follow Stream ↔ Stories.

import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { Filters } from "./stream";

export function useFilters() {
  const [params, setParams] = useSearchParams();
  const wilayas = params.getAll("w").join(",");
  const sources = params.getAll("s").join(",");
  const q = params.get("q") ?? "";

  const filters = useMemo<Filters>(
    () => ({
      wilayas: wilayas ? wilayas.split(",") : [],
      sources: sources ? sources.split(",") : [],
      q,
    }),
    [wilayas, sources, q],
  );

  const edit = useCallback(
    (change: (next: URLSearchParams) => void) =>
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          change(next);
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );

  const toggle = useCallback(
    (key: "w" | "s", value: string) =>
      edit((next) => {
        const current = next.getAll(key);
        next.delete(key);
        const kept = current.includes(value)
          ? current.filter((v) => v !== value)
          : [...current, value];
        kept.forEach((v) => next.append(key, v));
      }),
    [edit],
  );

  const toggleWilaya = useCallback((code: string) => toggle("w", code), [toggle]);
  const toggleSource = useCallback((slug: string) => toggle("s", slug), [toggle]);
  const clearFilters = useCallback(
    () =>
      edit((next) => {
        next.delete("w");
        next.delete("s");
      }),
    [edit],
  );
  const setQuery = useCallback(
    (value: string) =>
      edit((next) => {
        if (value) next.set("q", value);
        else next.delete("q");
      }),
    [edit],
  );

  const activeCount = filters.wilayas.length + filters.sources.length;
  return { filters, toggleWilaya, toggleSource, clearFilters, setQuery, activeCount };
}

/** The open article is in the URL too, so the back button closes the drawer on mobile. */
export function useOpenArticle() {
  const [params, setParams] = useSearchParams();
  const id = Number(params.get("article")) || null;
  const open = useCallback(
    (articleId: number) =>
      setParams((previous) => {
        const next = new URLSearchParams(previous);
        next.set("article", String(articleId));
        return next;
      }),
    [setParams],
  );
  const close = useCallback(
    () =>
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          next.delete("article");
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );
  return { id, open, close };
}
