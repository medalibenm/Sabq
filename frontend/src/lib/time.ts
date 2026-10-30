// Times are stored in UTC and always shown in Algiers time (docs/ui-design-prompt.md).

import { useSyncExternalStore } from "react";

import type { Lang } from "./text";

const TIME_ZONE = "Africa/Algiers";
const LOCALE: Record<Lang, string> = { ar: "ar-DZ-u-nu-latn", fr: "fr-DZ" };

const fmt = (lang: Lang, options: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat(LOCALE[lang], { timeZone: TIME_ZONE, ...options });

const hhmm = {
  ar: fmt("ar", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }),
  fr: fmt("fr", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }),
};
const hhmmss = {
  ar: fmt("ar", { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }),
  fr: fmt("fr", { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }),
};
const longDate = {
  ar: fmt("ar", { weekday: "long", day: "numeric", month: "long", year: "numeric" }),
  fr: fmt("fr", { weekday: "short", day: "numeric", month: "short", year: "numeric" }),
};
const shortDate = {
  ar: fmt("ar", { day: "numeric", month: "long", year: "numeric" }),
  fr: fmt("fr", { day: "numeric", month: "short", year: "numeric" }),
};

export const clock = (iso: string, lang: Lang) => hhmm[lang].format(new Date(iso));
export const clockSeconds = (iso: string, lang: Lang) => hhmmss[lang].format(new Date(iso));
export const date = (iso: string, lang: Lang) => shortDate[lang].format(new Date(iso));

export function exact(iso: string, lang: Lang): string {
  const day = longDate[lang].format(new Date(iso));
  return lang === "ar"
    ? `${day}، ${clock(iso, lang)} بتوقيت الجزائر`
    : `${day}, ${clock(iso, lang)} (heure d’Alger)`;
}

/** "منذ 3 د" / "il y a 3 min". `seconds` keeps precision under a minute (source checks). */
export function relative(iso: string, now: number, lang: Lang, seconds = false): string {
  const s = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 1000));
  const ar = lang === "ar";
  if (s < 60) {
    if (seconds) return ar ? `منذ ${s} ث` : `il y a ${s} s`;
    return ar ? "الآن" : "à l’instant";
  }
  const m = Math.floor(s / 60);
  if (m < 60) return ar ? `منذ ${m} د` : `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return ar ? `منذ ${h} س` : `il y a ${h} h`;
  const d = Math.floor(h / 24);
  return ar ? `منذ ${d} ي` : `il y a ${d} j`;
}

/** Published vs first seen, small in the drawer. Null when there is no meaningful gap. */
export function detectionGap(publishedIso: string, seenIso: string, lang: Lang): string | null {
  const s = (new Date(seenIso).getTime() - new Date(publishedIso).getTime()) / 1000;
  if (s < 0 || s > 2 * 86400) return null; // clock skew, or stored on a source's first poll
  const m = Math.round(s / 60);
  if (m < 1) return lang === "ar" ? "رُصد خلال أقل من دقيقة" : "détecté en moins d’une minute";
  if (m < 60) return lang === "ar" ? `رُصد بعد ${m} د` : `détecté ${m} min après`;
  const h = Math.round(m / 60);
  return lang === "ar" ? `رُصد بعد ${h} س` : `détecté ${h} h après`;
}

// One clock for the page, so relative times tick without each one holding a timer.
const listeners = new Set<() => void>();
let current = Date.now();

setInterval(() => {
  current = Date.now();
  listeners.forEach((listener) => listener());
}, 15_000);

export function useNow(): number {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}
