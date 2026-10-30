import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api } from "../api/client";
import type { ArticleDetail } from "../api/client";
import { contentAttrs } from "../lib/text";
import { clock, clockSeconds, detectionGap } from "../lib/time";
import { useOpenArticle } from "../lib/useFilters";
import { usePrefs } from "../prefs";
import { isEstimated } from "./ArticleCard";
import { ContentText, LangTag, Moment, SourceImage, WilayaChips } from "./bits";
import { Close, External, Layers, Pencil, Spinner } from "./icons";

function EditedLabel({ article }: { article: ArticleDetail }) {
  const { L, lang, count } = usePrefs();
  const edits = count("edits", article.version - 1);
  return (
    <span className="edited large">
      <Pencil size={12} />
      {edits}
      {article.modified_at && ` · ${L.lastEdit} ${clock(article.modified_at, lang)}`}
    </span>
  );
}

function Content({ article }: { article: ArticleDetail }) {
  const { L, lang } = usePrefs();
  const { open } = useOpenArticle();
  const estimated = isEstimated(article.published_at_confidence);
  const gap = estimated ? null : detectionGap(article.sort_at, article.first_seen_at, lang);
  const peers = article.same_story ?? [];
  return (
    <>
      <div className="drawer-scroll">
        <SourceImage key={article.id} src={article.image_url} className="drawer-image" />
        <div className="card-meta">
          <bdi className="strong">{article.source.name}</bdi>
          <LangTag language={article.language} />
          {article.version > 1 && <EditedLabel article={article} />}
        </div>
        <ContentText as="h2" language={article.language} className="drawer-title">
          {article.title}
        </ContentText>
        {article.lead && (
          <ContentText as="p" language={article.language} className="drawer-lead">
            {article.lead}
          </ContentText>
        )}
        {article.wilayas.length > 0 && (
          <div className="chips">
            <WilayaChips codes={article.wilayas} />
          </div>
        )}
        <dl className="facts">
          <div>
            <dt>{L.published}</dt>
            <dd>
              <span className="fact-time">
                {estimated ? `≈ ${clock(article.sort_at, lang)}` : clockSeconds(article.sort_at, lang)}
              </span>
              {estimated && <span className="faint"> · {L.estimated}</span>}
            </dd>
          </div>
          <div>
            <dt>{L.seen}</dt>
            <dd>
              <span className="fact-time">{clockSeconds(article.first_seen_at, lang)}</span>
              {gap && <span className="faint">{gap}</span>}
            </dd>
          </div>
          {article.author && (
            <div>
              <dt>{L.author}</dt>
              <dd className="fact-text">
                <bdi>{article.author}</bdi>
              </dd>
            </div>
          )}
          {article.section && (
            <div>
              <dt>{L.section}</dt>
              <dd className="fact-text">
                <bdi>{article.section}</bdi>
              </dd>
            </div>
          )}
        </dl>
        <p className="timezone-note">{L.allTimesAlgiers}</p>

        {peers.length > 0 && (
          <section aria-labelledby="same-story" className="same-story">
            <h3 id="same-story">
              <Layers />
              {L.sameStory} ({peers.length})
            </h3>
            {peers.map((peer) => (
              <button type="button" key={peer.id} onClick={() => open(peer.id)}>
                <span className="same-meta">
                  <bdi className="strong">{peer.source.name}</bdi>
                  <LangTag language={peer.language} small />
                  <Moment iso={peer.sort_at} estimated={isEstimated(peer.published_at_confidence)} />
                </span>
                <span className="same-title" {...contentAttrs(peer.language)}>
                  {peer.title}
                </span>
              </button>
            ))}
          </section>
        )}
      </div>
      <div className="drawer-foot">
        <a className="btn primary open-original" href={article.url} target="_blank" rel="noopener noreferrer">
          {L.openOriginalLong}
          <External size={18} width={2.2} />
        </a>
        <span className="opens-on">
          {L.opensOn} <bdi>{article.source.name}</bdi>
        </span>
      </div>
    </>
  );
}

export function Drawer() {
  const { L } = usePrefs();
  const { id, close } = useOpenArticle();
  const closeButton = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);
  const query = useQuery({
    queryKey: ["article", id],
    queryFn: () => api.article(id as number),
    enabled: id != null,
    retry: false,
  });

  const isOpen = id != null;
  useEffect(() => {
    if (!isOpen) return;
    opener.current = document.activeElement;
    closeButton.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && close();
    document.addEventListener("keydown", onKey);
    document.body.classList.add("no-scroll");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("no-scroll");
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
  }, [isOpen, close]);

  if (!isOpen) return null;
  return (
    <>
      <button type="button" className="scrim drawer-scrim" aria-label={L.close} onClick={close} />
      <aside className="drawer" aria-label={L.detail} role="dialog" aria-modal="true">
        <div className="drawer-top">
          <button ref={closeButton} type="button" className="icon-btn" aria-label={L.close} onClick={close}>
            <Close size={20} width={2.2} />
          </button>
          <span>{L.detail}</span>
        </div>
        {query.data ? (
          <Content article={query.data} />
        ) : (
          <div className="drawer-state">
            {query.isError ? <p>{L.articleGone}</p> : <Spinner size={20} />}
          </div>
        )}
      </aside>
    </>
  );
}
