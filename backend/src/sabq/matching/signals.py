"""Signals per article for story matching (docs/story-matching.md, pipeline step 2), from the
normalised title + lead. Stored in `articles.match_signals`; used as evidence and as conflict
checks (a different number of the same kind, another wilaya, another date, another country).

  numbers    [value, unit]  "15 قتيلا" -> [15, "قتيل"]; years -> [2026, "year"]
  dates      [day, month]   "12 اكتوبر" / "12 octobre" -> [12, 10]
  wilayas    codes named in the text (from the wilayas table; never the source's wilaya)
  countries  ISO codes of foreign countries named in the text
  entities   ids of a few officials and institutions (ar and fr names -> one id)

Deliberately small and cheap (v1). A conflict only sends a pair to review; it never merges.
"""

import re
from dataclasses import asdict, dataclass, field

from sabq.extract.text import clean_text
from sabq.matching.normalize import normalize

_NUMBER = re.compile(r"^\d+(?:[.,]\d+)?$")
_PREFIXES = ("وب", "ول", "فب", "وال", "بال", "لل", "و", "ب", "ل", "ف", "ك")

MONTHS = {
    # Maghreb (Algerian press), Mashriq, French; normalised spellings
    "جانفي": 1,
    "يناير": 1,
    "janvier": 1,
    "فيفري": 2,
    "فبراير": 2,
    "fevrier": 2,
    "مارس": 3,
    "mars": 3,
    "افريل": 4,
    "ابريل": 4,
    "avril": 4,
    "ماي": 5,
    "مايو": 5,
    "mai": 5,
    "جوان": 6,
    "يونيو": 6,
    "juin": 6,
    "جويليه": 7,
    "يوليو": 7,
    "juillet": 7,
    "اوت": 8,
    "اغسطس": 8,
    "aout": 8,
    "سبتمبر": 9,
    "septembre": 9,
    "اكتوبر": 10,
    "octobre": 10,
    "نوفمبر": 11,
    "novembre": 11,
    "ديسمبر": 12,
    "decembre": 12,
}

COUNTRIES = {
    "ma": ["المغرب", "maroc"],
    "tn": ["تونس", "tunisie"],
    "ly": ["ليبيا", "libye"],
    "eg": ["مصر", "egypte"],
    "mr": ["موريتانيا", "mauritanie"],
    "ml": ["مالي", "mali"],
    "ne": ["النيجر", "niger"],
    "fr": ["فرنسا", "france"],
    "es": ["اسبانيا", "espagne"],
    "it": ["ايطاليا", "italie"],
    "de": ["المانيا", "allemagne"],
    "gb": ["بريطانيا", "royaume uni"],
    "us": ["الولايات المتحده", "امريكا", "etats unis"],
    "ru": ["روسيا", "russie"],
    "cn": ["الصين", "chine"],
    "tr": ["تركيا", "turquie"],
    "sa": ["السعوديه", "arabie saoudite"],
    "qa": ["قطر", "qatar"],
    "ae": ["الامارات", "emirats"],
    "ps": ["فلسطين", "palestine"],
    "il": ["اسرائيل", "israel"],
    "sy": ["سوريا", "syrie"],
    "lb": ["لبنان", "liban"],
    "iq": ["العراق", "irak"],
    "ir": ["ايران", "iran"],
    "jo": ["الاردن", "jordanie"],
    "ye": ["اليمن", "yemen"],
    "sd": ["السودان", "soudan"],
    "nl": ["هولندا", "pays bas"],
    "be": ["بلجيكا", "belgique"],
    "pt": ["البرتغال", "portugal"],
    "ca": ["كندا", "canada"],
    "jp": ["اليابان", "japon"],
    "in": ["الهند", "inde"],
    "br": ["البرازيل", "bresil"],
    "za": ["جنوب افريقيا", "afrique du sud"],
    "ng": ["نيجيريا", "nigeria"],
    "sn": ["السنغال", "senegal"],
    "ua": ["اوكرانيا", "ukraine"],
    "kw": ["الكويت", "koweit"],
    "om": ["سلطنه عمان", "oman"],
    "ve": ["فنزويلا", "venezuela"],
    "ch": ["سويسرا", "suisse"],
}

ENTITIES = {
    "president": ["رئيس الجمهورية", "تبون", "tebboune", "president de la republique"],
    "prime-minister": ["الوزير الاول", "premier ministre"],
    "council-of-ministers": ["مجلس الوزراء", "conseil des ministres"],
    "anp": ["الجيش الوطني الشعبي", "anp"],
    "apn": ["المجلس الشعبي الوطني", "apn"],
    "senate": ["مجلس الامه", "conseil de la nation"],
    "sonatrach": ["سوناطراك", "sonatrach"],
    "sonelgaz": ["سونلغاز", "sonelgaz"],
    "un": ["الامم المتحده", "nations unies", "onu"],
    "african-union": ["الاتحاد الافريقي", "union africaine"],
}

# "الجزائر" / "Algérie" is the country far more often than wilaya 16: never a wilaya signal.
NOT_A_WILAYA = {"الجزاير", "algerie", "وطني", "national"}


@dataclass
class Signals:
    numbers: list[list] = field(default_factory=list)
    dates: list[list[int]] = field(default_factory=list)
    wilayas: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict | None) -> "Signals":
        return cls(**(data or {}))


class Gazetteer:
    """Wilaya names (Arabic and French, normalised) -> code, from the `wilayas` table rows."""

    def __init__(self, wilayas: list[tuple[str, str, str]]):  # (code, name_ar, name_fr)
        self.names: dict[str, str] = {}
        for code, name_ar, name_fr in wilayas:
            if code == "00":
                continue
            for name in (name_ar, name_fr):
                key = normalize(name)
                if key and key not in NOT_A_WILAYA:
                    self.names[key] = code
                    if key.startswith("ال"):  # "باتنه" also written without the article
                        self.names.setdefault(key[2:], code)
        self.longest = max((len(n.split()) for n in self.names), default=1)


def _variants(word: str) -> list[str]:
    """The word and the word without one leading Arabic prefix (و ب ل ف ك, وال, بال...)."""
    out = [word]
    for prefix in _PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 3:
            out.append(word[len(prefix) :])
            if not word[len(prefix) :].startswith("ال"):
                out.append("ال" + word[len(prefix) :])
    return out


def _unit(word: str) -> str:
    for prefix in ("ال", "و", "ب"):
        if word.startswith(prefix) and len(word) > len(prefix) + 2:
            word = word[len(prefix) :]
    for suffix in ("ين", "ون", "ات", "ا"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)]
    return word


def _phrases(words: list[str], longest: int) -> set[str]:
    found = set()
    for size in range(1, longest + 1):
        for start in range(len(words) - size + 1):
            chunk = words[start : start + size]
            if size == 1:
                found.update(_variants(chunk[0]))
            else:
                for first in _variants(chunk[0]):
                    found.add(" ".join([first, *chunk[1:]]))
    return found


def extract(title: str, lead: str | None, gazetteer: Gazetteer) -> Signals:
    words = normalize(f"{title} {clean_text(lead)}").split()
    signals = Signals()
    for i, word in enumerate(words):
        if not _NUMBER.match(word):
            continue
        value = float(word.replace(",", "."))
        value = int(value) if value.is_integer() else value
        following = words[i + 1] if i + 1 < len(words) else ""
        if following in MONTHS and isinstance(value, int) and 1 <= value <= 31:
            signals.dates.append([value, MONTHS[following]])
        elif isinstance(value, int) and 1900 <= value <= 2100:
            signals.numbers.append([value, "year"])
        elif following and not _NUMBER.match(following):
            signals.numbers.append([value, _unit(following)])
    phrases = _phrases(words, max(gazetteer.longest, 3))
    signals.wilayas = sorted({code for name, code in gazetteer.names.items() if name in phrases})
    signals.countries = sorted(
        code for code, names in COUNTRIES.items() if any(normalize(n) in phrases for n in names)
    )
    signals.entities = sorted(
        entity for entity, names in ENTITIES.items() if any(normalize(n) in phrases for n in names)
    )
    signals.numbers = [list(x) for x in dict.fromkeys(map(tuple, signals.numbers))]
    signals.dates = [list(x) for x in dict.fromkeys(map(tuple, signals.dates))]
    return signals


def conflicts(a: Signals, b: Signals) -> list[str]:
    """Hard conflicts between two articles: evidence they report different events."""
    found = []
    units_a: dict[str, set] = {}
    units_b: dict[str, set] = {}
    for value, unit in a.numbers:
        units_a.setdefault(unit, set()).add(value)
    for value, unit in b.numbers:
        units_b.setdefault(unit, set()).add(value)
    for unit in units_a.keys() & units_b.keys():
        if not units_a[unit] & units_b[unit]:
            found.append(f"numbers: {sorted(units_a[unit])} vs {sorted(units_b[unit])} {unit}")
    pairs = (
        ("dates", a.dates, b.dates),
        ("wilayas", a.wilayas, b.wilayas),
        ("countries", a.countries, b.countries),
    )
    for name, left, right in pairs:
        left_set = {tuple(x) if isinstance(x, list) else x for x in left}
        right_set = {tuple(x) if isinstance(x, list) else x for x in right}
        if left_set and right_set and not left_set & right_set:
            found.append(f"{name}: {sorted(left_set)} vs {sorted(right_set)}")
    return found
