import { useState } from "react";

import type { Article, StoryPeer } from "../api/client";
import { useOpenArticle } from "../lib/useFilters";
import { contentAttrs } from "../lib/text";
import { usePrefs } from "../prefs";
import { ContentText, LangTag, Moment, SourceImage, WilayaChips } from "./bits";
import { Chevron, External, Layers, Pencil } from "./icons";

export const isEstimated = (confidence: string) => confidence === "first_seen";

function PeerRow({ peer }: { peer: StoryPeer }) {
  const { L } = usePrefs();
  const { open } = useOpenArticle();
  return (
    <li className="peer">
      <span className="peer-source">
        <bdi className="strong ellipsis">{peer.source.name}</bdi>
        <LangTag language={peer.language} small />
      </span>
      <span className="peer-time">
        <Moment iso={peer.sort_at} estimated={isEstimated(peer.published_at_confidence)} />
      </span>
      <button
        type="button"
        className="peer-title"
        {...contentAttrs(peer.language)}
        onClick={() => open(peer.id)}
      >
        {peer.title}
      </button>
      <a
        className="peer-link"
        href={peer.url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={L.openOriginal}
        title={L.openOriginal}
      >
        <External size={14} />
      </a>
    </li>
  );
}

export function ArticleCard({ article, isNew }: { article: Article; isNew?: boolean }) {
  const { L, count } = usePrefs();
  const { open } = useOpenArticle();
  const [expanded, setExpanded] = useState(false);
  const estimated = isEstimated(article.published_at_confidence);
  const peers = article.same_story ?? [];

  return (
    <article className={isNew ? "card is-new" : "card"}>
      <div className="card-body">
        <SourceImage src={article.image_url} className="thumb" />
        <div className="card-main">
          <div className="card-meta">
            <bdi className="card-source">{article.source.name}</bdi>
            <LangTag language={article.language} />
            <span aria-hidden="true" className="dot">
              ·
            </span>
            <Moment iso={article.sort_at} estimated={estimated} />
            {estimated && (
              <span className="faint" title={L.estimatedTitle}>
                {L.estimated}
              </span>
            )}
            {isNew && <span className="new-tag">{L.isNew}</span>}
            {article.version > 1 && (
              <span className="edited" title={L.editedTitle}>
                <Pencil size={12} />
                {L.edited}
              </span>
            )}
          </div>
          <h3 className="card-title">
            <button type="button" {...contentAttrs(article.language)} onClick={() => open(article.id)}>
              {article.title}
            </button>
          </h3>
          {article.lead && (
            <ContentText as="p" language={article.language} className="card-lead">
              {article.lead}
            </ContentText>
          )}
          <div className="card-foot">
            <WilayaChips codes={article.wilayas} />
            <a className="open-link" href={article.url} target="_blank" rel="noopener noreferrer">
              {L.openOriginal}
              <External size={14} />
            </a>
          </div>
        </div>
      </div>

      {peers.length > 0 && (
        <div className="group">
          <button
            type="button"
            className="group-toggle"
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            <span className="group-count">
              <Layers size={15} />
              {count("otherSources", peers.length)}
            </span>
            <span className="group-action">{expanded ? L.hide : L.show}</span>
            <Chevron className={expanded ? "chevron open" : "chevron"} />
          </button>
          {expanded && (
            <ul className="peers">
              {peers.map((peer) => (
                <PeerRow key={peer.id} peer={peer} />
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}

export function CardSkeleton({ image, width }: { image: boolean; width: string }) {
  return (
    <div className="card-body skeleton-card">
      {image && <div className="skeleton thumb" />}
      <div className="skeleton-lines">
        <div className="skeleton" style={{ width: 160, height: 10 }} />
        <div className="skeleton" style={{ width, height: 16 }} />
        <div className="skeleton" style={{ width: "92%", height: 10 }} />
        <div className="skeleton" style={{ width: "70%", height: 10 }} />
      </div>
    </div>
  );
}
