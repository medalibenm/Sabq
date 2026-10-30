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
| [docs/ui-design-prompt.md](docs/ui-design-prompt.md) | The design brief; the resulting design and handoff are in `sabq-design/` |

## Run it locally
Requires Docker. From the repository root:

```sh
cp .env.example .env          # then edit secrets
docker compose up -d --build  # db, migrate, app, worker, proxy, mailpit
curl http://localhost/health.json   # per-source page: http://localhost/health (Sabq team login)
```

- Web app: http://localhost · Team test UI: http://localhost/ui · API (with code reload): http://localhost:8010 (interactive docs at `/docs`; the frontend
  contract is `docs/openapi.json`) · Mailpit (dev emails, e.g. invite links): http://localhost:8025
- Frontend with hot reload (API in Docker): `cd frontend && npm install && npm run dev`, then
  http://localhost:5173. Tests: `npm test`. After an API change, run `npm run api` for the types.
  The app at http://localhost is a built image: `docker compose up -d --build proxy` to refresh it.
- Tests: `cd backend && uv run pytest`. Database tests need a **separate** database, because
  they empty tables: `DATABASE_URL=postgresql+psycopg://sabq:<password>@localhost:5440/sabq_test`
  (create it once: `docker compose exec db psql -U sabq -c "CREATE DATABASE sabq_test"`).
  Never point them at `sabq`, the dev database the test UI uses.
- Production uses `compose.yaml` only: `docker compose -f compose.yaml up -d`
- Admin commands (no admin UI yet), e.g.:
  ```sh
  docker compose run --rm -T app python -m sabq.cli catalog load
  docker compose run --rm -T app python -m sabq.cli catalog validate --live aps-ar
  docker compose run --rm -T app python -m sabq.cli org create tariq "Tariq News"
  docker compose run --rm -T app python -m sabq.cli org wilaya tariq 05
  docker compose run --rm -T app python -m sabq.cli org source tariq awras-ar
  docker compose run --rm -T app python -m sabq.cli user invite tariq owner@example.dz owner
  docker compose run --rm -T app python -m sabq.cli user admin team@example.dz   # Sabq team
  docker compose run --rm -T app python -m sabq.cli org show tariq
  ```

## Non-negotiable rules

1. Respect `robots.txt`, checked live. A disallowed site is refused, never worked around.
2. What organisations see shows only title, lead, image and a link to the original. Full text stays internal.
3. Low request rates and our own identifying User-Agent. These are sites we depend on.
