// Plurals and text direction. Arabic has six plural forms; numbers stay Latin in both languages.

export type Lang = "ar" | "fr";

/** Templates per plural category; `{n}` is the number. Missing categories fall back to `other`. */
export type Forms = Partial<Record<Intl.LDMLPluralRule, string>> & { other: string };

const rules: Record<Lang, Intl.PluralRules> = {
  ar: new Intl.PluralRules("ar"),
  fr: new Intl.PluralRules("fr"),
};

export function plural(lang: Lang, n: number, forms: Forms): string {
  return (forms[rules[lang].select(n)] ?? forms.other).replace("{n}", String(n));
}

export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));
}

/** Title and lead carry the article's own language, whatever the interface language is. */
export function contentAttrs(language: string): { lang: string; dir: "rtl" | "ltr" } {
  return { lang: language, dir: language === "ar" ? "rtl" : "ltr" };
}

export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return words
    .slice(0, 2)
    .map((word) => [...word][0] ?? "")
    .join(" ")
    .toUpperCase();
}
