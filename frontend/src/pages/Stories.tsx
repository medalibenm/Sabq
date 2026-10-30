import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
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
import { Check, Chevron, External, Layers } from "../components/icons";
import { CardSkeleton } from "../components/ArticleCard";
import { initials } from "../lib/text";
import { useFilters, useOpenArticle } from "../lib/useFilters";
import { usePrefs } from "../prefs";
import { ActiveFilters } from "./Radar";

const REFRESH_MS = 60_000;

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

function StoryRow({ story, expanded, onToggle }: { story: Story; expanded: boolean; onToggle: () => void }) {
  const { L, count } = usePrefs();
  const lead = story.articles.find((a) => a.id === story.representative_id) ?? story.articles[0];
  const sources = uniqueSources(story.articles);
  const wilayas = [...new Set(story.articles.flatMap((a) => a.wilayas))].sort();
  const latest = story.articles[story.articles.length - 1];
  return (
    <article className="story">
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

export function Stories() {
  const { L, count } = usePrefs();
  const { filters } = useFilters();
  const [state, setState] = useState<StoryState>("all");
  const [openId, setOpenId] = useState<number | "first" | null>("first");
  const stories = useQuery({
    queryKey: ["stories", filters, state],
    queryFn: () => api.stories(filters, state),
    refetchInterval: REFRESH_MS,
    placeholderData: (previous) => previous,
  });

  const rows = stories.data ?? [];
  const developing = rows.filter((story) => !story.closed).length;
  const expandedId = openId === "first" ? rows[0]?.id : openId;
  const summary = `${count("stories", rows.length)} · ${count("storiesDeveloping", developing)}`;

  return (
    <main className="main">
      <div className="stream wide">
        <div className="stream-head">
          <ActiveFilters />
        </div>
        <div className="stories-head">
          <span className="soft">{stories.isSuccess && summary}</span>
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
            onToggle={() => setOpenId(story.id === expandedId ? null : story.id)}
          />
        ))}
      </div>
    </main>
  );
}
