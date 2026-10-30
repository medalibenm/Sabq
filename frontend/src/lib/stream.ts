// The stream's rules, free of React so they are easy to test.

import type { Article } from "../api/client";

export interface Filters {
  wilayas: string[];
  sources: string[];
  q: string;
}

/** The server's filter, applied to live articles (the stream sends everything the org may see). */
export function matches(article: Article, filters: Filters): boolean {
  if (filters.wilayas.length && !article.wilayas.some((w) => filters.wilayas.includes(w))) {
    return false;
  }
  if (filters.sources.length && !filters.sources.includes(article.source.slug)) return false;
  const q = filters.q.trim().toLocaleLowerCase();
  if (q && !`${article.title} ${article.lead ?? ""}`.toLocaleLowerCase().includes(q)) return false;
  return true;
}

function newestFirst(a: Article, b: Article): number {
  const at = new Date(b.sort_at).getTime() - new Date(a.sort_at).getTime();
  return at || b.id - a.id;
}

/** Newest first, one row per article; on a clash the earlier list wins (it is the fresher). */
export function merge(...lists: Article[][]): Article[] {
  const byId = new Map<number, Article>();
  for (const list of lists) {
    for (const article of list) {
      if (!byId.has(article.id)) byId.set(article.id, article);
    }
  }
  return [...byId.values()].sort(newestFirst);
}

/** One card per story: the first article shown stands for it, the rest appear inside that card. */
export function oneCardPerStory(articles: Article[]): Article[] {
  const seen = new Set<number>();
  return articles.filter((article) => {
    const story = article.story_cluster_id;
    if (story == null) return true;
    if (seen.has(story)) return false;
    seen.add(story);
    return true;
  });
}

export interface Burst {
  source: string;
  count: number;
}

/** One source behind most of a large arrival (a regional daily uploading its edition). */
export function dominantSource(pending: Article[]): Burst | null {
  if (pending.length < 10) return null;
  const counts = new Map<string, number>();
  for (const article of pending) {
    counts.set(article.source.name, (counts.get(article.source.name) ?? 0) + 1);
  }
  const [source, count] = [...counts].sort((a, b) => b[1] - a[1])[0];
  return count / pending.length >= 0.6 ? { source, count } : null;
}
