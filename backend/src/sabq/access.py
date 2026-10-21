"""The one access rule for organisation-facing reads (docs/architecture.md, data model).

An organisation sees an article only if
  - the organisation is active,
  - it has the article's source enabled (organisation_sources), and
  - at least one of the article's wilayas is enabled for it (organisation_wilayas).
Every organisation-facing query starts from `visible_articles`; nothing else filters articles.
"""

from sqlalchemy import Select, and_, exists, select

from sabq.db.models import (
    Article,
    ArticleWilaya,
    Organisation,
    OrganisationSource,
    OrganisationWilaya,
)


def visible_articles(organisation_id: int) -> Select[tuple[Article]]:
    source_enabled = exists().where(
        OrganisationSource.organisation_id == organisation_id,
        OrganisationSource.source_id == Article.source_id,
        OrganisationSource.enabled.is_(True),
    )
    wilaya_enabled = exists().where(
        ArticleWilaya.article_id == Article.id,
        OrganisationWilaya.wilaya_id == ArticleWilaya.wilaya_id,
        OrganisationWilaya.organisation_id == organisation_id,
        OrganisationWilaya.enabled.is_(True),
    )
    organisation_active = exists().where(
        Organisation.id == organisation_id, Organisation.status == "active"
    )
    return select(Article).where(and_(organisation_active, source_enabled, wilaya_enabled))
