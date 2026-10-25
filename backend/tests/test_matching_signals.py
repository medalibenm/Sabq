"""M8 (1/4): normalisation and signals for story matching. No database, no API."""

import importlib.util

import pytest

from sabq.cli import DEFAULT_CATALOG
from sabq.matching.normalize import match_text, normalize, tokens
from sabq.matching.signals import Gazetteer, Signals, conflicts, extract

SEED = DEFAULT_CATALOG.parent / "backend/alembic/versions/20261021_0003_seed_wilayas.py"


def seed_wilayas() -> list[tuple[str, str, str]]:
    spec = importlib.util.spec_from_file_location("seed", SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.WILAYAS


GAZETTEER = Gazetteer(seed_wilayas())


# --- normalisation ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "عاجل: رئيسُ الجمهوريّة يستقبل سفيرة مملكة هولندا",
            "رييس الجمهوريه يستقبل سفيره مملكه هولندا",
        ),
        ("إطلاق أوّل مشروع بـ ٣٥ مليار دينار", "اطلاق اول مشروع ب 35 مليار دينار"),
        ("الـــجزائـر", "الجزاير"),  # tatweel
        ("Le Président reçoit l’ambassadeur – VIDÉO", "le president recoit l ambassadeur"),
        ("Sétif : 3,5 milliards pour l'eau", "setif 3 5 milliards pour l eau"),
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_tokens_drop_stopwords_and_match_text_joins_title_and_lead():
    assert tokens(normalize("وزير الداخلية في زيارة إلى ولاية سطيف اليوم")) == [
        "وزير",
        "الداخليه",
        "زياره",
        "ولايه",
        "سطيف",
    ]
    assert match_text("عنوان الخبر", "مقدمة الخبر") == "عنوان الخبر مقدمه الخبر"
    assert match_text("عنوان", None) == "عنوان"


# --- signals ---------------------------------------------------------------------------------


def test_numbers_dates_and_years():
    signals = extract("حادث مرور يخلف 15 قتيلا و3 جرحى يوم 12 أكتوبر 2026", None, GAZETTEER)
    assert [15, "قتيل"] in signals.numbers
    assert [12, 10] in signals.dates
    assert [2026, "year"] in signals.numbers
    french = extract("Accident : 15 morts le 12 octobre", None, GAZETTEER)
    assert french.dates == [[12, 10]] and [15, "morts"] in french.numbers


def test_wilayas_with_prefixes_multiword_and_algeria_is_not_a_wilaya():
    signals = extract("زلزال بقوة 4 درجات يضرب ولاية المدية وبسيدي بلعباس", None, GAZETTEER)
    assert signals.wilayas == ["22", "26"]  # Sidi Bel Abbès, Médéa
    assert extract("الجزائر تحتضن اجتماعا وزاريا", None, GAZETTEER).wilayas == []
    assert extract("Séisme à Médéa", None, GAZETTEER).wilayas == ["26"]
    assert extract("مشاريع جديدة بباتنة", None, GAZETTEER).wilayas == ["05"]
    assert extract("Barika et Bou Saâda", None, GAZETTEER).wilayas == ["60", "68"]  # new in 2027


def test_countries_and_entities():
    signals = extract("الرئيس تبون يستقبل سفير المغرب", "مجلس الوزراء", GAZETTEER)
    assert signals.countries == ["ma"]
    assert signals.entities == ["council-of-ministers", "president"]
    french = extract("Le président Tebboune reçoit l'ambassadeur du Maroc", None, GAZETTEER)
    assert french.countries == ["ma"] and french.entities == ["president"]  # ar = fr ids


def test_every_wilaya_name_is_found():
    for code, name_ar, name_fr in seed_wilayas():
        if code in ("00", "16"):  # National; Algiers is "الجزائر", mostly the country
            continue
        assert code in extract(f"خبر من {name_ar}", None, GAZETTEER).wilayas, name_ar
        assert code in extract(f"Nouvelles de {name_fr}", None, GAZETTEER).wilayas, name_fr


# --- conflicts -------------------------------------------------------------------------------


def test_conflicts_are_found_only_when_both_sides_say_something_different():
    accident_a = extract("حادث مرور يخلف 15 قتيلا بولاية سطيف", None, GAZETTEER)
    accident_b = extract("حادث مرور يخلف 7 قتلى بولاية باتنة", None, GAZETTEER)
    found = conflicts(accident_a, accident_b)
    assert any(c.startswith("wilayas") for c in found)
    same = extract("مقتل 15 شخصا في حادث بسطيف", None, GAZETTEER)
    assert not any(c.startswith("wilayas") for c in conflicts(accident_a, same))
    assert conflicts(Signals(), accident_a) == []  # silence is not a conflict
    meeting_12 = extract("اجتماع مجلس الوزراء يوم 12 أكتوبر", None, GAZETTEER)
    meeting_19 = extract("اجتماع مجلس الوزراء يوم 19 أكتوبر", None, GAZETTEER)
    assert conflicts(meeting_12, meeting_19) == ["dates: [(12, 10)] vs [(19, 10)]"]
    morocco = extract("الرئيس يستقبل سفير المغرب", None, GAZETTEER)
    netherlands = extract("الرئيس يستقبل سفيرة هولندا", None, GAZETTEER)
    assert conflicts(morocco, netherlands) == ["countries: ['ma'] vs ['nl']"]


def test_signals_round_trip_json():
    signals = extract("15 قتيلا في سطيف يوم 12 أكتوبر", None, GAZETTEER)
    assert Signals.from_json(signals.to_json()) == signals
