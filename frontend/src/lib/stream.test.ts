import { describe, expect, it } from "vitest";

import type { Article, Story } from "../api/client";
import {
  dominantSource,
  matches,
  merge,
  oneCardPerStory,
  sameRows,
  storiesAfterReveal,
  updatedStories,
} from "./stream";
import { plural } from "./text";
import { clock, detectionGap, exact, relative } from "./time";

function article(id: number, extra: Partial<Article> = {}): Article {
  return {
    id,
    title: `عنوان ${id}`,
    lead: null,
    image_url: null,
    url: `https://example.dz/${id}`,
    source: { slug: "aps-ar", name: "APS", language: "ar" },
    wilayas: ["00"],
    language: "ar",
    section: null,
    published_at: null,
    published_at_confidence: "source_meta",
    first_seen_at: "2026-10-28T18:00:00Z",
    sort_at: `2026-10-28T18:${String(id).padStart(2, "0")}:00Z`,
    modified_at: null,
    version: 1,
    ...extra,
  } as Article;
}

const none = { wilayas: [], sources: [], q: "" };

describe("live articles and filters", () => {
  it("applies the same rules as the server", () => {
    const a = article(1, { wilayas: ["05", "19"], lead: "Intempéries à Batna" });
    expect(matches(a, none)).toBe(true);
    expect(matches(a, { ...none, wilayas: ["19", "17"] })).toBe(true);
    expect(matches(a, { ...none, wilayas: ["17"] })).toBe(false);
    expect(matches(a, { ...none, sources: ["other"] })).toBe(false);
    expect(matches(a, { ...none, q: "intempéries" })).toBe(true);
    expect(matches(a, { ...none, q: "تلفريك" })).toBe(false);
  });
});

describe("the list", () => {
  it("merges newest first, once per article, the fresher copy winning", () => {
    const fresh = article(2, { title: "edited" });
    const merged = merge([fresh], [article(2), article(1), article(3)]);
    expect(merged.map((a) => a.id)).toEqual([3, 2, 1]);
    expect(merged[1].title).toBe("edited");
  });

  it("keeps one card per story, the newest", () => {
    const list = [
      article(5, { story_cluster_id: 9 }),
      article(4),
      article(3, { story_cluster_id: 9 }),
    ];
    expect(oneCardPerStory(list).map((a) => a.id)).toEqual([5, 4]);
  });

  it("names the source of a burst, not of a mixed arrival", () => {
    const from = (name: string) => article(1, { source: { slug: name, name, language: "ar" } });
    const burst = [...Array(58).fill(from("Awras")), ...Array(2).fill(from("APS"))];
    expect(dominantSource(burst)).toEqual({ source: "Awras", count: 58 });
    expect(dominantSource([from("Awras"), from("Awras")])).toBeNull();
    expect(
      dominantSource([...Array(6).fill(from("Awras")), ...Array(6).fill(from("APS"))]),
    ).toBeNull();
  });
});

describe("Algiers time", () => {
  const iso = "2026-10-28T18:04:12Z"; // 19:04 in Algiers (UTC+1, no daylight saving)

  it("shows Algiers time in both languages, with Latin digits", () => {
    expect(clock(iso, "fr")).toBe("19:04");
    expect(clock(iso, "ar")).toBe("19:04");
    expect(exact(iso, "ar")).toContain("بتوقيت الجزائر");
    expect(exact(iso, "ar")).toContain("2026");
  });

  it("gives relative times", () => {
    const at = (s: number) => new Date(iso).getTime() + s * 1000;
    expect(relative(iso, at(10), "ar")).toBe("الآن");
    expect(relative(iso, at(40), "ar", true)).toBe("منذ 40 ث");
    expect(relative(iso, at(180), "ar")).toBe("منذ 3 د");
    expect(relative(iso, at(180), "fr")).toBe("il y a 3 min");
    expect(relative(iso, at(7200), "fr")).toBe("il y a 2 h");
    expect(relative(iso, at(-500), "fr")).toBe("à l’instant");
  });

  it("shows the detection gap only when it means something", () => {
    expect(detectionGap(iso, "2026-10-28T18:05:12Z", "ar")).toBe("رُصد بعد 1 د");
    expect(detectionGap(iso, "2026-10-28T18:00:00Z", "ar")).toBeNull();
    expect(detectionGap(iso, "2026-11-10T18:00:00Z", "ar")).toBeNull();
  });
});

describe("Arabic plurals", () => {
  const forms = {
    one: "مقال جديد",
    two: "مقالان جديدان",
    few: "{n} مقالات جديدة",
    many: "{n} مقالًا جديدًا",
    other: "{n} مقال جديد",
  };

  it("picks the right form", () => {
    expect(plural("ar", 1, forms)).toBe("مقال جديد");
    expect(plural("ar", 2, forms)).toBe("مقالان جديدان");
    expect(plural("ar", 5, forms)).toBe("5 مقالات جديدة");
    expect(plural("ar", 60, forms)).toBe("60 مقالًا جديدًا");
    expect(plural("ar", 100, forms)).toBe("100 مقال جديد");
  });
});

describe("events waiting for the reader", () => {
  const story = (id: number, ...articles: number[]) =>
    ({ id, articles: articles.map((a) => article(a)) }) as Story;

  it("finds new stories and stories with new articles, nothing else", () => {
    const shown = [story(1, 1, 2), story(2, 3, 4)];
    const fresh = [story(3, 7, 8), story(2, 3, 4, 9), story(1, 1, 2)];
    expect(updatedStories(shown, fresh).map((s) => s.id)).toEqual([3, 2]);
    expect(updatedStories(shown, shown)).toEqual([]);
  });

  it("puts the updated stories first when revealed", () => {
    const fresh = [story(1, 1, 2), story(2, 3, 4), story(3, 5, 6)];
    const after = storiesAfterReveal(fresh, [story(3, 5, 6)]);
    expect(after.map((s) => s.id)).toEqual([3, 1, 2]);
  });

  it("only treats the same order as safe to swap silently", () => {
    const a = story(1, 1, 2);
    const b = story(2, 3, 4);
    expect(sameRows([a, b], [a, b])).toBe(true);
    expect(sameRows([a, b], [b, a])).toBe(false);
    expect(sameRows([a, b], [a])).toBe(false);
  });
});
