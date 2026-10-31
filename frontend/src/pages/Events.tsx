import { useEffect, useMemo, useState } from "react";

import type { Article, Story, StoryState } from "../api/client";
import { isEstimated } from "../components/ArticleCard";
import {
  Clockface,
  ContentText,
  LangTag,
  LoadError,
  Moment,
  Segmented,
  WilayaChips,
} from "../components/bits";
import { ArrowUp, Check, Chevron, External, Layers } from "../components/icons";
import { CardSkeleton } from "../components/ArticleCard";
import { STORIES_LIMIT, useStories } from "../components/ViewSwitch";
import { sameRows, storiesAfterReveal, updatedStories } from "../lib/stream";
import { initials } from "../lib/text";
import { useFilters, useOpenArticle } from "../lib/useFilters";
import { usePrefs } from "../prefs";

const HIGHLIGHT_MS = 8000;

function uniqueSources(articles: Article[]) {
  return [...new Map(articles.map((a) => [a.source.slug, a.source])).values()];
}

function languageMix(articles: Article[]) {
  const counts = new Map<string, number>();
  articles.forEach((a) => counts.set(a.language, (counts.get(a.language) ?? 0) + 1));
  return [...counts].map(([language, n]) => `${n} ${language.toUpperCase()}`).join(" · ");
}

function Timeline({ articles }: { articles: Article[] }) {
  const { L } = usePrefs();
  const { open } = useOpenArticle();
  return (
    <ol className="timeline">
      {articles.map((article, index) => (
        <li key={article.id}>
          <div className="timeline-time">
            <Clockface iso={article.sort_at} />
            {index === 0 && <span className="first-tag">{L.firstTag}</span>}
          </div>
          <div className="timeline-body">
            <span className="same-meta">
              <bdi className="strong">{article.source.name}</bdi>
              <LangTag language={article.language} small />
              {isEstimated(article.published_at_confidence) && (
                <span className="faint" title={L.estimatedTitle}>
                  {L.estimated}
                </span>
              )}
            </span>
            <h3>
              <button
                type="button"
                lang={article.language}
                dir={article.language === "ar" ? "rtl" : "ltr"}
                onClick={() => open(article.id)}
              >
                {article.title}
              </button>
            </h3>
            {article.lead && (
              <ContentText as="p" language={article.language}>
                {article.lead}
              </ContentText>
            )}
          </div>
          <a
            className="timeline-link"
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={L.openOriginal}
            title={L.openOriginal}
          >
            <External />
          </a>
        </li>
      ))}
    </ol>
  );
}

function StoryRow({
  story,
  expanded,
  isNew,
  onToggle,
}: {
  story: Story;
  expanded: boolean;
  isNew: boolean;
  onToggle: () => void;
}) {
  const { L, count } = usePrefs();
  const lead = story.articles.find((a) => a.id === story.representative_id) ?? story.articles[0];
  const sources = uniqueSources(story.articles);
  const wilayas = [...new Set(story.articles.flatMap((a) => a.wilayas))].sort();
  const latest = story.articles[story.articles.length - 1];
  return (
    <article id={`event-${story.id}`} className={isNew ? "story is-new" : "story"}>
      <button type="button" className="story-head" aria-expanded={expanded} onClick={onToggle}>
        <div className="story-main">
          <div className="story-tags">
            {story.closed ? (
              <span className="tag closed">
                <Check size={12} width={2.4} />
                {L.closed}
              </span>
            ) : (
              <span className="tag developing">
                <span className="tag-dot" aria-hidden="true" />
                {L.developing}
              </span>
            )}
            <span className="soft">{count("sources", sources.length)}</span>
            <span aria-hidden="true" className="dot">
              ·
            </span>
            <span className="mix latin" dir="ltr">
              {languageMix(story.articles)}
            </span>
          </div>
          <ContentText as="h2" language={lead.language} className="story-title">
            {lead.title}
          </ContentText>
          <div className="story-sources">
            <span className="marks" aria-hidden="true">
              {sources.slice(0, 5).map((source, index) => (
                <span key={source.slug} className={`mark m${index % 4}`}>
                  {initials(source.name).replace(" ", "")}
                </span>
              ))}
            </span>
            <span className="soft">
              <bdi>{sources.map((source) => source.name).join(" · ")}</bdi>
            </span>
          </div>
        </div>
        <div className="story-side">
          <span>
            <span className="story-side-label">{L.firstReport}</span>
            <strong>
              <Clockface iso={story.articles[0].sort_at} />
            </strong>
          </span>
          <span>
            <span className="story-side-label">{L.lastUpdate}</span>
            <strong>
              <Moment iso={story.last_member_at ?? latest.sort_at} />
            </strong>
          </span>
          <span className="chips">
            <WilayaChips codes={wilayas} />
          </span>
        </div>
        <Chevron size={18} className={expanded ? "chevron open" : "chevron"} />
      </button>
      {expanded && <Timeline articles={story.articles} />}
    </article>
  );
}

export type OpenEvent = number | "first" | null;

/** The Events view. Like the stream, it never moves by itself: fresh data is compared with what
 * is on screen, and changes wait in the pill until the reader asks for them. */
export function EventsView({
  state,
  setState,
  openId,
  setOpenId,
  focusId,
  onFocused,
}: {
  state: StoryState;
  setState: (state: StoryState) => void;
  openId: OpenEvent;
  setOpenId: (id: OpenEvent) => void;
  focusId: number | null;
  onFocused: () => void;
}) {
  const { L, count } = usePrefs();
  const { filters } = useFilters();
  const stories = useStories(state);
  const [held, setHeld] = useState<{ key: string; rows: Story[] } | null>(null);
  const [highlighted, setHighlighted] = useState<Set<number>>(new Set());

  const key = JSON.stringify([filters, state]);
  const fresh = stories.isPlaceholderData ? undefined : stories.data;
  const rows = held?.key === key ? held.rows : (stories.data ?? []);
  const updates = useMemo(
    () => (fresh && held?.key === key ? updatedStories(held.rows, fresh) : []),
    [fresh, held, key],
  );

  useEffect(() => {
    if (!fresh) return;
    const untouched = held?.key === key && sameRows(held.rows, fresh) && updates.length === 0;
    if (held?.key !== key || (untouched && held.rows !== fresh)) setHeld({ key, rows: fresh });
  }, [fresh, held, key, updates]);

  const reveal = () => {
    if (!fresh) return;
    setHeld({ key, rows: storiesAfterReveal(fresh, updates) });
    setHighlighted(new Set(updates.map((story) => story.id)));
    window.scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => setHighlighted(new Set()), HIGHLIGHT_MS);
  };

  // arriving from the strip above the stream: the event may be newer than this list
  useEffect(() => {
    if (focusId === null) return;
    if (!rows.some((story) => story.id === focusId)) {
      if (fresh?.some((story) => story.id === focusId)) setHeld({ key, rows: fresh });
      return;
    }
    document.getElementById(`event-${focusId}`)?.scrollIntoView({ block: "start" });
    onFocused();
  }, [focusId, rows, fresh, key, onFocused]);

  const developing = rows.filter((story) => !story.closed).length;
  const expandedId = openId === "first" ? rows[0]?.id : openId;
  const summary = `${count("stories", rows.length)} · ${count("storiesDeveloping", developing)}`;

  return (
    <>
      <div className="stories-head">
        <span className="soft">{stories.isSuccess && rows.length < STORIES_LIMIT && summary}</span>
        <Segmented<StoryState>
          label={L.storyState}
          value={state}
          onChange={setState}
          className="compact"
          options={[
            { value: "all", label: L.all },
            { value: "developing", label: L.developing },
            { value: "closed", label: L.closed },
          ]}
        />
      </div>

      {updates.length > 0 && (
        <div className="pill-anchor">
          <button type="button" className="pill" onClick={reveal}>
            <ArrowUp width={2.4} />
            <span>
              <strong>{count("eventsUpdated", updates.length)}</strong>
            </span>
          </button>
        </div>
      )}

      {stories.isPending && (
        <div aria-busy="true" aria-label={L.loading} className="skeletons">
          <CardSkeleton image={false} width="80%" />
          <CardSkeleton image={false} width="66%" />
          <CardSkeleton image={false} width="72%" />
        </div>
      )}
      {stories.isError && <LoadError onRetry={() => stories.refetch()} />}
      {stories.isSuccess && rows.length === 0 && (
        <section className="empty">
          <span className="empty-icon">
            <Layers size={22} />
          </span>
          <h2>{L.noStoriesTitle}</h2>
          <p>{L.noStoriesBody}</p>
        </section>
      )}
      {rows.map((story) => (
        <StoryRow
          key={story.id}
          story={story}
          expanded={story.id === expandedId}
          isNew={highlighted.has(story.id)}
          onToggle={() => setOpenId(story.id === expandedId ? null : story.id)}
        />
      ))}
    </>
  );
}
