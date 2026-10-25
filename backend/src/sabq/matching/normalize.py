"""Text normalisation for matching only (docs/story-matching.md, pipeline step 1). Stored text is
never changed; the result goes to `articles.match_text`.

Arabic: no diacritics or tatweel, أ إ آ ٱ → ا, ى → ي, ة → ه, ؤ → و, ئ → ي. French: no accents,
one apostrophe. Both: NFC, lower case, Arabic-Indic digits → 0-9, punctuation and boilerplate
("عاجل", "فيديو", "Urgent"...) removed. `tokens` also drops stopwords.
"""

import re
import unicodedata

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARABIC_LETTERS = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي", "ـ": ""}
)
_TASHKEEL = re.compile("[\u064b-\u065f\u0670\u06d6-\u06ed]")  # harakat, Quranic marks
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'"})
_PUNCTUATION = re.compile(r"[^\w\s']|_", re.UNICODE)
_SPACES = re.compile(r"\s+")

# Labels sites put around titles; matched as whole normalised tokens.
BOILERPLATE = {
    "عاجل",
    "فيديو",
    "بالفيديو",
    "بالصور",
    "صور",
    "حصري",
    "مباشر",
    "تحديث",
    "urgent",
    "video",
    "vidéo",
    "direct",
    "exclusif",
    "photos",
    "aps",
    "apsar",
}

STOPWORDS_AR = {
    "في",
    "من",
    "الي",
    "علي",
    "عن",
    "مع",
    "هذا",
    "هذه",
    "ذلك",
    "تلك",
    "التي",
    "الذي",
    "الذين",
    "و",
    "او",
    "ثم",
    "قد",
    "لقد",
    "كان",
    "كانت",
    "يكون",
    "ان",
    "انه",
    "انها",
    "لا",
    "لم",
    "لن",
    "ما",
    "هو",
    "هي",
    "هم",
    "كما",
    "بعد",
    "قبل",
    "بين",
    "حول",
    "خلال",
    "حتي",
    "عند",
    "منذ",
    "اليوم",
    "امس",
    "غدا",
    "كل",
    "بعض",
    "اي",
    "اكثر",
    "اقل",
    "ب",
    "ل",
    "ف",
    "ك",
    "يا",
    "لدي",
    "وفق",
    "ضمن",
    "اجل",
    "الا",
    "اذا",
    "ولا",
    "وقد",
    "وهو",
    "وهي",
    "ومن",
    "وفي",
}
STOPWORDS_FR = {
    "le",
    "la",
    "les",
    "l",
    "un",
    "une",
    "des",
    "de",
    "du",
    "d",
    "et",
    "ou",
    "a",
    "au",
    "aux",
    "en",
    "dans",
    "par",
    "pour",
    "sur",
    "avec",
    "sans",
    "sous",
    "ce",
    "cette",
    "ces",
    "qui",
    "que",
    "qu",
    "dont",
    "est",
    "sont",
    "ont",
    "se",
    "sa",
    "son",
    "ses",
    "leur",
    "leurs",
    "il",
    "elle",
    "ils",
    "elles",
    "on",
    "ne",
    "pas",
    "plus",
    "lors",
    "apres",
    "avant",
    "entre",
    "aujourd'hui",
    "hier",
    "demain",
    "y",
    "s",
    "n",
    "c",
    "j",
    "m",
    "t",
}
STOPWORDS = STOPWORDS_AR | STOPWORDS_FR


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    kept = []
    for char in decomposed:
        # drop Latin combining accents only; Arabic marks are handled by _TASHKEEL
        if unicodedata.combining(char) and not ("؀" <= char <= "ۿ"):
            continue
        kept.append(char)
    return unicodedata.normalize("NFC", "".join(kept))


def normalize(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).casefold().translate(_DIGITS)
    text = _TASHKEEL.sub("", text).translate(_ARABIC_LETTERS)
    text = _strip_accents(text).translate(_APOSTROPHES)
    text = _PUNCTUATION.sub(" ", text).replace("'", " ")
    words = [w for w in _SPACES.split(text) if w and w not in BOILERPLATE]
    return " ".join(words)


def tokens(normalized: str) -> list[str]:
    """Content words: no stopwords, no 1-letter words. Arabic `و`/`ب`/`ل` prefixes are kept
    (stemming would merge different words; the embedding handles morphology)."""
    return [w for w in normalized.split() if len(w) > 1 and w not in STOPWORDS]


def match_text(title: str, lead: str | None) -> str:
    return f"{normalize(title)} {normalize(lead)}".strip()
