// The stream: newest first, infinite scroll. New articles never move the list: they wait in the
// pill until the reader asks for them (docs/ui-design-prompt.md, "New articles while reading").

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Article } from "../api/client";
import { ArticleCard, CardSkeleton } from "../components/ArticleCard";
import { LoadError, Loading, useWilayaLabel } from "../components/bits";
import { useFacets } from "../components/FilterRail";
import { ArrowUp, Close, Funnel, Radar as RadarIcon, Search } from "../components/icons";
import { useLive } from "../live";
import { dominantSource, matches, merge, oneCardPerStory } from "../lib/stream";
import { fill } from "../lib/text";
import { useFilters } from "../lib/useFilters";
import { usePrefs } from "../prefs";

const HIGHLIGHT_MS = 8000;
const FEW_ARTICLES = 3;

export function ActiveFilters() {
  const { L } = usePrefs();
  const { filters, toggleWilaya, toggleSource, clearFilters, activeCount } = useFilters();
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const wilayaLabel = useWilayaLabel();
  if (activeCount === 0) return <span className="scope">{L.allScope}</span>;
  const sourceName = (slug: string) => sources.data?.find((s) => s.slug === slug)?.name ?? slug;
  return (
    <>
      {filters.wilayas.map((code) => (
        <button
          type="button"
          key={code}
          className="filter-chip"
          aria-label={`${L.removeFilter} ${wilayaLabel(code)}`}
          onClick={() => toggleWilaya(code)}
        >
          <span>{wilayaLabel(code)}</span>
          <Close size={12} width={2.4} />
        </button>
      ))}
      {filters.sources.map((slug) => (
        <button
          type="button"
          key={slug}
          className="filter-chip"
          aria-label={`${L.removeFilter} ${sourceName(slug)}`}
          onClick={() => toggleSource(slug)}
        >
          <bdi>{sourceName(slug)}</bdi>
          <Close size={12} width={2.4} />
        </button>
      ))}
      <button type="button" className="link" onClick={clearFilters}>
        {L.clearAll}
      </button>
    </>
  );
}

function Empty({ onClearSearch, onClearFilters }: { onClearSearch: () => void; onClearFilters: () => void }) {
  const { L } = usePrefs();
  const { filters } = useFilters();
  const q = filters.q.trim();
  return (
    <section className="empty">
      <span className="empty-icon">{q ? <Search size={22} /> : <Funnel size={22} />}</span>
      <h2>{q ? fill(L.noResultsTitle, { q }) : L.emptyTitle}</h2>
      <p>{q ? L.noResultsBody : L.emptyBody}</p>
      <button type="button" className="btn primary" onClick={q ? onClearSearch : onClearFilters}>
        {q ? L.noResultsAction : L.emptyAction}
      </button>
    </section>
  );
}

function FirstTime() {
  const { L, count } = usePrefs();
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const wilayas = useQuery({ queryKey: ["wilayas"], queryFn: api.wilayas });
  return (
    <section className="first-time">
      <span className="first-icon">
        <RadarIcon size={20} />
      </span>
      <div>
        <h2>{L.ftTitle}</h2>
        <p>
          {fill(L.ftBody, {
            sources: count("sources", sources.data?.length ?? 0),
            wilayas: count("wilayas", wilayas.data?.length ?? 0),
          })}
        </p>
        <Link to="/sources">{L.ftLink}</Link>
      </div>
    </section>
  );
}

const SKELETONS = [
  { image: true, width: "82%" },
  { image: false, width: "64%" },
  { image: true, width: "74%" },
  { image: false, width: "88%" },
  { image: true, width: "58%" },
];

export function Radar() {
  const { L, count } = usePrefs();
  const { filters, clearFilters, setQuery, activeCount } = useFilters();
  const { subscribe, resets } = useLive();
  const client = useQueryClient();
  const facets = useFacets();

  const list = useInfiniteQuery({
    queryKey: ["articles", filters],
    queryFn: ({ pageParam }) => api.articles(filters, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: Infinity, // only the reader moves the list
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const [pending, setPending] = useState<Article[]>([]);
  const [revealed, setRevealed] = useState<Article[]>([]);
  const [highlighted, setHighlighted] = useState<Set<number>>(new Set());
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  useEffect(() => {
    setPending([]);
    setRevealed([]);
    setHighlighted(new Set());
  }, [filters]);

  useEffect(
    () =>
      subscribe((article) => {
        if (matches(article, filtersRef.current)) {
          setPending((current) => merge([article], current));
        }
      }),
    [subscribe],
  );

  const firstReset = useRef(resets);
  useEffect(() => {
    if (resets === firstReset.current) return;
    firstReset.current = resets;
    client.resetQueries({ queryKey: ["articles"] });
  }, [resets, client]);

  const loaded = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data]);
  const visible = useMemo(() => oneCardPerStory(merge(revealed, loaded)), [revealed, loaded]);
  const waiting = useMemo(() => {
    const known = new Set(merge(revealed, loaded).map((article) => article.id));
    return pending.filter((article) => !known.has(article.id));
  }, [pending, revealed, loaded]);

  const reveal = async () => {
    const arrived = waiting;
    setRevealed((current) => merge(arrived, current));
    setHighlighted(new Set(arrived.map((article) => article.id)));
    setPending([]);
    window.scrollTo({ top: 0, behavior: "smooth" });
    client.invalidateQueries({ queryKey: ["facets"] });
    setTimeout(() => setHighlighted(new Set()), HIGHLIGHT_MS);
    try {
      // the first page again: stories may have formed since these articles were pushed
      const fresh = await api.articles(filtersRef.current);
      setRevealed((current) => merge(fresh.items, current));
    } catch {
      // the pushed copies are good enough
    }
  };

  const sentinel = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = list;
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasNextPage) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !isFetchingNextPage) fetchNextPage();
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const burst = dominantSource(waiting);
  const isFirstTime =
    list.isSuccess &&
    !hasNextPage &&
    visible.length <= FEW_ARTICLES &&
    activeCount === 0 &&
    !filters.q.trim();
  const isEmpty = list.isSuccess && visible.length === 0;

  return (
    <main className="main">
      <div className="stream">
        <div className="stream-head">
          <ActiveFilters />
          {facets.data && <span className="stream-count">{count("articlesToday", facets.data.total)}</span>}
        </div>

        {waiting.length > 0 && (
          <div className="pill-anchor">
            <button type="button" className="pill" onClick={reveal}>
              <ArrowUp width={2.4} />
              <span>
                <strong>{count("newArticles", waiting.length)}</strong>
                {burst && <small>{fill(L.burstSub, { count: burst.count, source: burst.source })}</small>}
              </span>
            </button>
          </div>
        )}

        {isFirstTime && <FirstTime />}

        {list.isPending && (
          <div aria-busy="true" aria-label={L.loading} className="skeletons">
            {SKELETONS.map((skeleton) => (
              <CardSkeleton key={skeleton.width} {...skeleton} />
            ))}
          </div>
        )}

        {list.isError && <LoadError onRetry={() => list.refetch()} />}

        {isEmpty && !isFirstTime && (
          <Empty onClearFilters={clearFilters} onClearSearch={() => setQuery("")} />
        )}

        {visible.map((article) => (
          <ArticleCard key={article.id} article={article} isNew={highlighted.has(article.id)} />
        ))}

        <div ref={sentinel} />
        {isFetchingNextPage && <Loading />}
      </div>
    </main>
  );
}
