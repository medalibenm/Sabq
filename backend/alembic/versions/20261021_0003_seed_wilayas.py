"""Seed the 69 wilayas and 00 National (decision 2026-10-19).

01-58: wilayas in force before the 2025 amendment of loi n° 84-09 (49-58 created in 2019/2021).
59-69: the 11 new wilayas, codes and names from the arrêté published in Journal officiel n° 50
of 15 July 2026 (French and Arabic editions); operational from 2027-01-01.
00: special row for sources without a local wilaya.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21
"""

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_WILAYAS_FROM = date(2027, 1, 1)

WILAYAS = [
    ("00", "وطني", "National"),
    ("01", "أدرار", "Adrar"),
    ("02", "الشلف", "Chlef"),
    ("03", "الأغواط", "Laghouat"),
    ("04", "أم البواقي", "Oum El Bouaghi"),
    ("05", "باتنة", "Batna"),
    ("06", "بجاية", "Béjaïa"),
    ("07", "بسكرة", "Biskra"),
    ("08", "بشار", "Béchar"),
    ("09", "البليدة", "Blida"),
    ("10", "البويرة", "Bouira"),
    ("11", "تمنراست", "Tamanrasset"),
    ("12", "تبسة", "Tébessa"),
    ("13", "تلمسان", "Tlemcen"),
    ("14", "تيارت", "Tiaret"),
    ("15", "تيزي وزو", "Tizi Ouzou"),
    ("16", "الجزائر", "Alger"),
    ("17", "الجلفة", "Djelfa"),
    ("18", "جيجل", "Jijel"),
    ("19", "سطيف", "Sétif"),
    ("20", "سعيدة", "Saïda"),
    ("21", "سكيكدة", "Skikda"),
    ("22", "سيدي بلعباس", "Sidi Bel Abbès"),
    ("23", "عنابة", "Annaba"),
    ("24", "قالمة", "Guelma"),
    ("25", "قسنطينة", "Constantine"),
    ("26", "المدية", "Médéa"),
    ("27", "مستغانم", "Mostaganem"),
    ("28", "المسيلة", "M'Sila"),
    ("29", "معسكر", "Mascara"),
    ("30", "ورقلة", "Ouargla"),
    ("31", "وهران", "Oran"),
    ("32", "البيض", "El Bayadh"),
    ("33", "إليزي", "Illizi"),
    ("34", "برج بوعريريج", "Bordj Bou Arréridj"),
    ("35", "بومرداس", "Boumerdès"),
    ("36", "الطارف", "El Tarf"),
    ("37", "تندوف", "Tindouf"),
    ("38", "تيسمسيلت", "Tissemsilt"),
    ("39", "الوادي", "El Oued"),
    ("40", "خنشلة", "Khenchela"),
    ("41", "سوق أهراس", "Souk Ahras"),
    ("42", "تيبازة", "Tipaza"),
    ("43", "ميلة", "Mila"),
    ("44", "عين الدفلى", "Aïn Defla"),
    ("45", "النعامة", "Naâma"),
    ("46", "عين تموشنت", "Aïn Témouchent"),
    ("47", "غرداية", "Ghardaïa"),
    ("48", "غليزان", "Relizane"),
    ("49", "تيميمون", "Timimoun"),
    ("50", "برج باجي مختار", "Bordj Badji Mokhtar"),
    ("51", "أولاد جلال", "Ouled Djellal"),
    ("52", "بني عباس", "Béni Abbès"),
    ("53", "عين صالح", "In Salah"),
    ("54", "عين قزام", "In Guezzam"),
    ("55", "تقرت", "Touggourt"),
    ("56", "جانت", "Djanet"),
    ("57", "المغير", "El M'Ghair"),
    ("58", "المنيعة", "El Meniaa"),
    ("59", "أفلو", "Aflou"),
    ("60", "بريكة", "Barika"),
    ("61", "القنطرة", "El Kantara"),
    ("62", "بئر العاتر", "Bir El Ater"),
    ("63", "العريشة", "El Aricha"),
    ("64", "قصر الشلالة", "Ksar Chellala"),
    ("65", "عين وسارة", "Aïn Ouessara"),
    ("66", "مسعد", "Messaad"),
    ("67", "قصر البخاري", "Ksar El Boukhari"),
    ("68", "بوسعادة", "Bou Saâda"),
    ("69", "الأبيض سيدي الشيخ", "El Abiodh Sidi Cheikh"),
]

wilayas = sa.table(
    "wilayas",
    sa.column("code", sa.String),
    sa.column("name_ar", sa.String),
    sa.column("name_fr", sa.String),
    sa.column("active_from", sa.Date),
)


def upgrade() -> None:
    op.bulk_insert(
        wilayas,
        [
            {
                "code": code,
                "name_ar": name_ar,
                "name_fr": name_fr,
                "active_from": NEW_WILAYAS_FROM if int(code) >= 59 else None,
            }
            for code, name_ar, name_fr in WILAYAS
        ],
    )


def downgrade() -> None:
    op.execute(wilayas.delete().where(wilayas.c.code.in_([code for code, _, _ in WILAYAS])))
