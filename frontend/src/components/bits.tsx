// Small pieces shared by the screens.

import { useState } from "react";
import type { ReactNode } from "react";

import { clock, exact, relative, useNow } from "../lib/time";
import { contentAttrs } from "../lib/text";
import { usePrefs } from "../prefs";
import { Spinner, StateOk, StateStopped, Clock } from "./icons";

export function LangTag({ language, small }: { language: string; small?: boolean }) {
  const { L } = usePrefs();
  return (
    <span className={small ? "lang-tag small" : "lang-tag"} title={L.articleLanguage}>
      {language.toUpperCase()}
    </span>
  );
}

export function Moment({ iso, estimated }: { iso: string; estimated?: boolean }) {
  const { lang, L } = usePrefs();
  const now = useNow();
  const title = exact(iso, lang);
  return (
    <time
      dateTime={iso}
      className={estimated ? "estimated" : undefined}
      title={estimated ? `${title} — ${L.estimatedTitle}` : title}
    >
      {estimated ? "≈ " : ""}
      {relative(iso, now, lang)}
    </time>
  );
}

export function Clockface({ iso }: { iso: string }) {
  const { lang } = usePrefs();
  return (
    <time dateTime={iso} title={exact(iso, lang)} className="latin">
      {clock(iso, lang)}
    </time>
  );
}

export function WilayaChips({ codes }: { codes: string[] }) {
  const { lang } = usePrefs();
  const label = useWilayaLabel();
  return (
    <>
      {codes.map((code) => (
        <span className="chip" key={code} lang={lang}>
          {label(code)}
        </span>
      ))}
    </>
  );
}

// filled by App once /app/wilayas has loaded; articles may mention wilayas outside the grant
const wilayaNames = new Map<string, { name_ar: string; name_fr: string }>();

export function rememberWilayas(list: { code: string; name_ar: string; name_fr: string }[]) {
  list.forEach((w) => wilayaNames.set(w.code, w));
}

export function useWilayaLabel() {
  const { lang } = usePrefs();
  return (code: string) => {
    const wilaya = wilayaNames.get(code);
    if (!wilaya) return code;
    return `${code} ${lang === "ar" ? wilaya.name_ar : wilaya.name_fr}`;
  };
}

/** A source's image; nothing at all when there is none or it fails, so the card stays whole. */
export function SourceImage({ src, className }: { src: string | null; className: string }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return null;
  return (
    <img
      className={className}
      src={src}
      alt=""
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}

export function ContentText({
  as: Tag,
  language,
  className,
  children,
}: {
  as: "p" | "h2" | "h3" | "span";
  language: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Tag {...contentAttrs(language)} className={className}>
      {children}
    </Tag>
  );
}

export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  className = "",
}: {
  label: string;
  options: { value: T; label: string; lang?: string }[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={`segmented ${className}`}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          lang={option.lang}
          aria-checked={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function StateBadge({ state }: { state: string }) {
  const { L } = usePrefs();
  if (state === "stopped") {
    return (
      <span className="state bad">
        <StateStopped size={15} width={2.4} />
        {L.stateStopped}
      </span>
    );
  }
  if (state === "delayed") {
    return (
      <span className="state warn">
        <Clock size={15} width={2.4} />
        {L.stateDelayed}
      </span>
    );
  }
  return (
    <span className="state ok">
      <StateOk size={15} width={2.4} />
      {L.stateOk}
    </span>
  );
}

export function Loading() {
  const { L } = usePrefs();
  return (
    <div className="loading-row" role="status">
      <Spinner />
      <span>{L.loadingMore}</span>
    </div>
  );
}

export function LoadError({ onRetry }: { onRetry: () => void }) {
  const { L } = usePrefs();
  return (
    <section className="empty" role="alert">
      <p>{L.loadFailed}</p>
      <button type="button" className="btn primary" onClick={onRetry}>
        {L.retry}
      </button>
    </section>
  );
}
