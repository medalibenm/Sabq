# Sabq | سبق

A news radar for newsrooms. Sabq watches official and news sources (including sites that publish no RSS), detects new articles within a minute or two, and serves them to journalists in a web app (behind login) and as alerts.

Sabq is built for multiple organisations from the start, using one shared source catalog with
wilaya-based access separation.

> Status: **build phase started** (2026-10-19), see [docs/plan.md](docs/plan.md). A proof of concept on 6 sites validated the approach; see [docs/poc-lessons.md](docs/poc-lessons.md).

## Documentation

| Doc | What it covers |
|---|---|
| [docs/plan.md](docs/plan.md) | Build plan and SOP: source investigation track, backend milestones, status |
| [docs/product.md](docs/product.md) | What Sabq is, who it's for, scope, product decisions, content rules |
| [docs/architecture.md](docs/architecture.md) | How ingestion works: the layers, source config, data model, feeds, validation, health and repair |
| [docs/story-matching.md](docs/story-matching.md) | Cross-source deduplication: detecting articles from different sources about the same event |
| [docs/adding-sources.md](docs/adding-sources.md) | How we add a source to the catalog today (manual investigation with Claude Code) |
| [docs/sources.md](docs/sources.md) | The source catalog: verified sources and candidates to probe |
| [docs/ai-investigation.md](docs/ai-investigation.md) | The automated AI investigation and repair design (deferred) |
| [docs/decisions.md](docs/decisions.md) | Decision log and open questions |
| [docs/poc-lessons.md](docs/poc-lessons.md) | What the proof of concept proved, site by site |

## Run it locally
Requires Docker. From the repository root:

```sh
cp .env.example .env          # then edit secrets
docker compose up -d --build  # db, migrate, app, worker, proxy, mailpit
curl http://localhost/health.json
```

- API (with code reload): http://localhost:8010 · Mailpit (dev emails): http://localhost:8025
- Tests: `cd backend && uv run pytest` (database tests need
  `DATABASE_URL=postgresql+psycopg://sabq:<password>@localhost:5440/sabq`)
- Production uses `compose.yaml` only: `docker compose -f compose.yaml up -d`
- Admin commands (no admin UI yet), e.g.:
  ```sh
  docker compose run --rm -T app python -m sabq.cli catalog load
  docker compose run --rm -T app python -m sabq.cli catalog validate --live aps-ar
  docker compose run --rm -T app python -m sabq.cli org create tariq "Tariq News"
  docker compose run --rm -T app python -m sabq.cli org wilaya tariq 05
  docker compose run --rm -T app python -m sabq.cli org source tariq awras-ar
  docker compose run --rm -T app python -m sabq.cli user create tariq editor@example.dz editor
  docker compose run --rm -T app python -m sabq.cli org show tariq
  ```

## Non-negotiable rules

1. Respect `robots.txt`, checked live. A disallowed site is refused, never worked around.
2. What organisations see shows only title, lead, image and a link to the original. Full text stays internal.
3. Low request rates and our own identifying User-Agent. These are sites we depend on.
