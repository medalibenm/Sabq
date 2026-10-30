import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Source, Wilaya } from "../api/client";
import { fill } from "../lib/text";
import { useFilters } from "../lib/useFilters";
import { usePrefs } from "../prefs";
import { Check, Chevron, Close, Funnel, Panel, Search, StateStopped } from "./icons";

const SOURCES_SHOWN = 5;
const WILAYAS_SHOWN = 3;
const FACETS_REFRESH_MS = 60_000;

export function useFacets() {
  const { filters } = useFilters();
  return useQuery({
    queryKey: ["facets", filters],
    queryFn: () => api.facets(filters),
    refetchInterval: FACETS_REFRESH_MS,
    placeholderData: (previous) => previous,
  });
}

function Box({ on }: { on: boolean }) {
  return <span className={on ? "box on" : "box"}>{on && <Check size={12} width={3.4} />}</span>;
}

/** Selected items stay visible; the others are capped until "show more". */
function capped<T>(items: T[], limit: number, all: boolean, isOn: (item: T) => boolean) {
  const shown = all ? items : items.filter((item, i) => i < limit || isOn(item));
  return { shown, hidden: items.length - shown.length, extra: items.length > limit };
}

function More({
  all,
  hidden,
  onToggle,
}: {
  all: boolean;
  hidden: number;
  onToggle: () => void;
}) {
  const { L } = usePrefs();
  return (
    <button type="button" className="rail-more" aria-expanded={all} onClick={onToggle}>
      <Chevron size={14} width={2.4} className={all ? "chevron open" : "chevron"} />
      {all ? L.less : fill(L.more, { n: hidden })}
    </button>
  );
}

function SourceRow({ source, n, on, toggle }: { source: Source; n: number; on: boolean; toggle: () => void }) {
  const { L } = usePrefs();
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={on}
      className={on ? "rail-row on" : "rail-row"}
      onClick={toggle}
    >
      <Box on={on} />
      <span className="rail-name ellipsis">
        <bdi>{source.name}</bdi>
      </span>
      {source.state === "stopped" && (
        <span className="rail-stopped" title={L.stoppedTitle}>
          <StateStopped size={11} width={2.6} />
          {L.stopped}
        </span>
      )}
      <span className="lang-tag small">{source.language.toUpperCase()}</span>
      <span className="rail-count">{n}</span>
    </button>
  );
}

function WilayaRow({ wilaya, n, on, toggle }: { wilaya: Wilaya; n: number; on: boolean; toggle: () => void }) {
  const { lang } = usePrefs();
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={on}
      className={on ? "rail-row on" : "rail-row"}
      onClick={toggle}
    >
      <Box on={on} />
      <span className="rail-code latin">{wilaya.code}</span>
      <span className="rail-name">{lang === "ar" ? wilaya.name_ar : wilaya.name_fr}</span>
      <span className="rail-count">{n}</span>
    </button>
  );
}

function RailContent() {
  const { L } = usePrefs();
  const { filters, toggleSource, toggleWilaya } = useFilters();
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources, refetchInterval: 60_000 });
  const wilayas = useQuery({ queryKey: ["wilayas"], queryFn: api.wilayas });
  const facets = useFacets().data;
  const [search, setSearch] = useState("");
  const [allSources, setAllSources] = useState(false);
  const [allWilayas, setAllWilayas] = useState(false);

  const sourceN = (s: Source) => facets?.sources[s.slug] ?? 0;
  const wilayaN = (w: Wilaya) => facets?.wilayas[w.code] ?? 0;
  const busiestSources = [...(sources.data ?? [])].sort((a, b) => sourceN(b) - sourceN(a));
  const busiestWilayas = [...(wilayas.data ?? [])].sort((a, b) => wilayaN(b) - wilayaN(a));

  const needle = search.trim().toLocaleLowerCase();
  const sourceOn = (s: Source) => filters.sources.includes(s.slug);
  const wilayaOn = (w: Wilaya) => filters.wilayas.includes(w.code);
  const found = busiestSources.filter((s) => s.name.toLocaleLowerCase().includes(needle));
  const sourceList = needle
    ? { shown: found, hidden: 0, extra: false }
    : capped(found, SOURCES_SHOWN, allSources, sourceOn);
  const wilayaList = capped(busiestWilayas, WILAYAS_SHOWN, allWilayas, wilayaOn);

  return (
    <div className="rail-scroll">
      <section aria-labelledby="rail-sources" className="rail-section">
        <div className="rail-head">
          <h3 id="rail-sources">{L.sources}</h3>
          <span>{L.today}</span>
        </div>
        <div className="rail-search">
          <Search size={14} width={2.2} />
          <input
            type="search"
            aria-label={L.searchSources}
            placeholder={L.searchSources}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        {sourceList.shown.map((source) => (
          <SourceRow
            key={source.slug}
            source={source}
            n={sourceN(source)}
            on={sourceOn(source)}
            toggle={() => toggleSource(source.slug)}
          />
        ))}
        {needle && found.length === 0 && <p className="rail-none">{L.noSource}</p>}
        {sourceList.extra && (
          <More all={allSources} hidden={sourceList.hidden} onToggle={() => setAllSources(!allSources)} />
        )}
      </section>

      <section aria-labelledby="rail-wilayas" className="rail-section">
        <div className="rail-head">
          <h3 id="rail-wilayas">{L.wilayas}</h3>
          <span>{L.today}</span>
        </div>
        {wilayaList.shown.map((wilaya) => (
          <WilayaRow
            key={wilaya.code}
            wilaya={wilaya}
            n={wilayaN(wilaya)}
            on={wilayaOn(wilaya)}
            toggle={() => toggleWilaya(wilaya.code)}
          />
        ))}
        {wilayaList.extra && (
          <More all={allWilayas} hidden={wilayaList.hidden} onToggle={() => setAllWilayas(!allWilayas)} />
        )}
      </section>
    </div>
  );
}

const startsCollapsed = () => {
  try {
    const saved = localStorage.getItem("sabq.rail");
    if (saved) return saved === "collapsed";
  } catch {
    // no storage: fall back to the screen width
  }
  return window.innerWidth < 1180;
};

export function FilterRail() {
  const { L } = usePrefs();
  const { activeCount } = useFilters();
  const [collapsed, setCollapsed] = useState(startsCollapsed);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("sabq.rail", next ? "collapsed" : "open");
    } catch {
      // the choice lasts until the page closes
    }
  };

  if (collapsed) {
    return (
      <aside aria-label={L.filters} className="rail collapsed">
        <button type="button" className="rail-expand" aria-label={L.expand} onClick={toggle}>
          <Funnel size={18} />
          {activeCount > 0 && <span className="count-badge floating">{activeCount}</span>}
        </button>
      </aside>
    );
  }
  return (
    <aside aria-label={L.filters} className="rail">
      <div className="rail-top">
        <h2>{L.filters}</h2>
        {activeCount > 0 && <span className="count-badge">{activeCount}</span>}
        <span className="grow" />
        <button type="button" className="icon-btn small" aria-label={L.collapse} onClick={toggle}>
          <Panel size={18} />
        </button>
      </div>
      <RailContent />
    </aside>
  );
}

export function FilterSheet({ onClose }: { onClose: () => void }) {
  const { L, count } = usePrefs();
  const { activeCount, clearFilters } = useFilters();
  const total = useFacets().data?.total ?? 0;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.classList.add("no-scroll");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("no-scroll");
    };
  }, [onClose]);

  return (
    <>
      <button type="button" className="scrim" aria-label={L.close} onClick={onClose} />
      <aside aria-label={L.filters} className="sheet" role="dialog" aria-modal="true">
        <div className="sheet-handle" aria-hidden="true">
          <span />
        </div>
        <div className="rail-top">
          <h2>{L.filters}</h2>
          {activeCount > 0 && <span className="count-badge">{activeCount}</span>}
          <span className="grow" />
          <button type="button" className="icon-btn" aria-label={L.close} onClick={onClose}>
            <Close size={18} width={2.2} />
          </button>
        </div>
        <RailContent />
        <div className="sheet-foot">
          <button type="button" className="btn ghost tall grow" onClick={clearFilters}>
            {L.clear}
          </button>
          <button type="button" className="btn primary tall grow2" onClick={onClose}>
            {count("showArticles", total)}
          </button>
        </div>
      </aside>
    </>
  );
}
