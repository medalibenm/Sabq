// The Radar: one page, two views of the same filtered articles. Articles is the stream, newest
// first, infinite scroll. New articles never move the list: they wait in the pill until the reader
// asks for them (docs/ui-design-prompt.md, "New articles while reading"). Events groups them.
// Both views stay mounted, so switching keeps their lists, expansions and waiting pills.

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Article, Me, StoryState } from "../api/client";
import { ArticleCard, CardSkeleton } from "../components/ArticleCard";
import { LoadError, Loading, Moment, useWilayaLabel } from "../components/bits";
import { useFacets } from "../components/FilterRail";
import { ArrowUp, Close, Funnel, Radar as RadarIcon, Search } from "../components/icons";
import { useStories, ViewSwitch } from "../components/ViewSwitch";
import { developingStrip } from "../lib/flags";
import { useLive } from "../live";
import { dominantSource, matches, merge, oneCardPerStory } from "../lib/stream";
import { contentAttrs, fill } from "../lib/text";
import { useFilters } from "../lib/useFilters";
import { useRadarView } from "../lib/useRadarView";
import type { RadarView } from "../lib/useRadarView";
import { usePrefs } from "../prefs";
import { EventsView } from "./Events";
import type { OpenEvent } from "./Events";

const HIGHLIGHT_MS = 8000;
const FEW_ARTICLES = 3;
const STRIP_EVENTS = 3;
const STORIES_DEBOUNCE_MS = 5000;

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

/** Up to three developing events above the stream (behind a flag, see lib/flags.ts). */
function DevelopingStrip({ onOpen }: { onOpen: (id: number) => void }) {
  const { L, count } = usePrefs();
  const stories = useStories("all");
  const developing = (stories.data ?? []).filter((story) => !story.closed).slice(0, STRIP_EVENTS);
  if (developing.length === 0) return null;
  return (
    <section className="dev-strip" aria-label={L.developing}>
      <span className="dev-strip-title">
        <span className="tag-dot" aria-hidden="true" />
        {L.developing}
      </span>
      {developing.map((story) => {
        const lead =
          story.articles.find((a) => a.id === story.representative_id) ?? story.articles[0];
        const sources = new Set(story.articles.map((a) => a.source.slug)).size;
        const latest = story.articles[story.articles.length - 1];
        return (
          <button type="button" key={story.id} onClick={() => onOpen(story.id)}>
            <span {...contentAttrs(lead.language)}>{lead.title}</span>
            <small>
              {count("sources", sources)} · <Moment iso={story.last_member_at ?? latest.sort_at} />
            </small>
          </button>
        );
      })}
    </section>
  );
}

function ArticlesView({ onOpenEvent }: { onOpenEvent: (id: number) => void }) {
  const { L, count } = usePrefs();
  const { filters, clearFilters, setQuery, activeCount } = useFilters();
  const { subscribe, resets } = useLive();
  const client = useQueryClient();

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
    <>
      {developingStrip && <DevelopingStrip onOpen={onOpenEvent} />}

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
    </>
  );
}

const typing = (target: HTMLElement) =>
  /INPUT|TEXTAREA|SELECT/.test(target.tagName) || target.isContentEditable;

export function Radar({ me }: { me: Me }) {
  const { L, count } = usePrefs();
  const { filters } = useFilters();
  const { subscribe } = useLive();
  const client = useQueryClient();
  const facets = useFacets();
  const { view, setView, putInUrl, inUrl } = useRadarView(me.id);
  const [eventState, setEventState] = useState<StoryState>("all");
  const [openEvent, setOpenEvent] = useState<OpenEvent>("first");
  const [focusEvent, setFocusEvent] = useState<number | null>(null);

  // the address always names the view, so what is on screen can be linked
  useEffect(() => {
    if (!inUrl) putInUrl(view);
  }, [inUrl, view, putInUrl]);

  // each view keeps its own place on the page; different filters mean a different list
  const scroll = useRef<Partial<Record<RadarView, number>>>({});
  const current = useRef(view);
  useLayoutEffect(() => {
    if (current.current === view) return;
    current.current = view;
    window.scrollTo(0, scroll.current[view] ?? 0);
  }, [view]);
  useEffect(() => {
    const onScroll = () => {
      scroll.current[current.current] = window.scrollY;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => {
    scroll.current = {};
  }, [filters]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // "ر" is the same key on an Arabic keyboard
      if (!["v", "V", "ر"].includes(event.key)) return;
      if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
      if (typing(event.target as HTMLElement) || document.querySelector('[role="dialog"]')) return;
      setView(current.current === "articles" ? "events" : "articles");
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setView]);

  // a new article may have joined an event: look again, once a burst has passed
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const stop = subscribe(() => {
      clearTimeout(timer);
      timer = setTimeout(
        () => client.invalidateQueries({ queryKey: ["stories"] }),
        STORIES_DEBOUNCE_MS,
      );
    });
    return () => {
      clearTimeout(timer);
      stop();
    };
  }, [subscribe, client]);

  const onOpenEvent = useCallback(
    (id: number) => {
      setEventState("all");
      setOpenEvent(id);
      setFocusEvent(id);
      setView("events");
    },
    [setView],
  );
  const onFocused = useCallback(() => setFocusEvent(null), []);

  return (
    <main className="main">
      <div className={view === "events" ? "stream wide" : "stream"}>
        <div className="stream-head">
          <div className="view-control">
            <ViewSwitch userId={me.id} className="desktop-only" />
            <span className="sort-note">{view === "events" ? L.sortUpdated : L.sortNewest}</span>
          </div>
          <ActiveFilters />
          {view === "articles" && facets.data && (
            <span className="stream-count">{count("articlesToday", facets.data.total)}</span>
          )}
        </div>

        <div className="radar-view" hidden={view !== "articles"}>
          <ArticlesView onOpenEvent={onOpenEvent} />
        </div>
        <div className="radar-view" hidden={view !== "events"}>
          <EventsView
            state={eventState}
            setState={setEventState}
            openId={openEvent}
            setOpenId={setOpenEvent}
            focusId={focusEvent}
            onFocused={onFocused}
          />
        </div>
      </div>
    </main>
  );
}
