# Automated AI investigation and repair

> Status: **designed, deferred.** Today a person investigates with Claude Code ([adding-sources.md](adding-sources.md)). Build this when repairs become frequent (automated repair first), or if self-service onboarding opens.

## Principle: our tools gather evidence, the LLM only judges
The LLM does not browse the web or run the whole investigation. **We build our own tools** that fetch, render, search and test. They collect and clean the evidence; the LLM reads **their output** and makes the judgment calls: which source holds the articles, which field is the title/date/image, how links are built.

Why our own tools and not the LLM provider's web fetching:
- **Control:** our User-Agent, robots check, rate limits and Algerian proxy apply to every request.
- **Raw evidence:** exact status codes, headers, raw HTML/JSON. Built-in fetchers return summaries.
- **Cost:** evidence is cleaned and shrunk first (scripts/styles stripped, JSON cut to 2–3 samples, bundles searched rather than sent). A raw 1.4 MB bundle would cost ~$1.60 per read; an excerpt costs cents.
- **Safety:** the LLM can only call our tools, only on the site being investigated.
- **Reuse:** the same tools serve validation, repairs and debugging, with or without AI.

Packaging: plain Python functions exposed through the Claude API's tool use. Wrap them in an MCP server later only if the team wants them in Claude Code or other agents.

## Tools

| Tool | What it does | What the LLM receives |
|---|---|---|
| `check_robots(url)` | Evaluates `robots.txt` and notices for our User-Agent | allowed/disallowed + rules (runs before any AI) |
| `fetch(url)` | Polite GET, our User-Agent, proxy if needed | status, headers, type, size, cleaned truncated body |
| `discover_feeds(url)` | Feed links (head and body), common paths, platform APIs, sitemaps | candidates, each with a test result |
| `detect_platform(url)` | WordPress, Next.js, Nuxt, Angular, Drupal… markers | platform + evidence |
| `extract_embedded_data(url)` | JSON-LD, `__NEXT_DATA__`, `self.__next_f`, `__NUXT__`… | article-like objects, a few samples |
| `browser_capture(url)` | Headless browser, records network requests | JSON requests (URL, status, sample items) |
| `search_bundle(url, pattern)` | Searches the site's JS bundles | matching snippets only |
| `test_config(config)` | Runs the extractor with a config | items or errors |
| `validate(config)` | Validation checks ([architecture.md](architecture.md#validating-a-config)) | pass/fail per check, with details |
| `submit_config(config)` | Final answer; input schema = our config format | validation report (loop ends when it passes) |

## How a run works
1. **Code first, no AI:** `check_robots` → `discover_feeds` → `detect_platform`. A feed or API that validates ends the run (AA, AFP, El Hayat cost $0 in AI).
2. **Code gathers evidence:** `extract_embedded_data`, `browser_capture`, `search_bundle` for known patterns.
3. **LLM reads the evidence:** asks for more (calls a tool) or proposes a config via `submit_config`.
4. **Code tests and validates;** results go back to the LLM.
5. Repeat 3–4 until validation passes (max ~10 turns), else alert a person.
6. CSS selector fallback uses the same tools (`fetch` gives cleaned HTML).

Every tool call, its output, token usage and the resulting config version are logged.

## One investigation = several API calls
The API is stateless: our code keeps the conversation (`messages`) and resends it each call. Each round adds the model's tool requests and our tool results.

| Site type | Example | AI calls |
|---|---|---|
| Feed or API found by code | AA, AFP, El Hayat | 0 |
| Embedded data already extracted | APS | 1–2 |
| Internal API hidden in JS | El Mouradia | 4–8 |

Example (El Mouradia): call 1 → `search_bundle("backendUrl")`; call 2 → `fetch` the API; call 3 → `submit_config` (fails: link format unknown); call 4 → `search_bundle("routerLink")`; call 5 → `submit_config` passes.

### Loop implementation (Claude API tool use)
- Tools described with name, description, input schema, `strict: true`.
- Loop: call the API; if `stop_reason == "tool_use"`, run every requested tool and send **all** `tool_result` blocks back in **one** user message; repeat.
- Errors are returned as tool results (`is_error: true`) so the model can correct itself.
- Exit via `submit_config` (structured, schema-valid config); validation errors are its tool result.
- Limits: max ~10 turns, truncated tool outputs, tools restricted to the site's hosts.
- Prompt caching on (resent history ~20× cheaper); fixed system prompt.
- The Anthropic SDK's tool runner can drive the loop; a hand-written loop gives full control.

Reference sketch (Python, Anthropic SDK):

```python
response = client.beta.messages.create(
    model="claude-opus-5-5", max_tokens=16000,
    system=INVESTIGATOR_PROMPT, tools=TOOLS, messages=messages,
    cache_control={"type": "ephemeral"},
    output_config={"effort": "high"},
    betas=["server-side-fallback-2026-07-01"], fallbacks="default",
)
messages.append({"role": "assistant", "content": response.content})
if response.stop_reason == "tool_use":
    results = [{"type": "tool_result", "tool_use_id": b.id,
                "content": run_tool(b.name, b.input)[:20_000]}
               for b in response.content if b.type == "tool_use"]
    messages.append({"role": "user", "content": results})
```

## Cost estimate (Opus 5.5, cleaned input, caching on; not yet measured)
Prices: $4 / $20 per million input/output tokens; cached input $0.20.

| Case | Tokens in / out | Cost |
|---|---|---|
| Feed/API found by code | ~5k / ~1k | $0–0.05 |
| AI investigation (6–10 turns) | ~150–300k / ~10–20k | ~$0.50–1.50 |
| CSS selector fallback | ~60–120k / ~5–10k | ~$0.30–0.70 |
| Repair after redesign | ~50–150k / ~5–10k | ~$0.30–1.00 |

≈ $1–5 per site per year (onboarding + a few repairs). Polling costs nothing in AI. Cheaper options: Haiku 5.5 for simple checks, lower effort for repairs, Sonnet 5.5 if quality holds. Measure on the PoC fixtures before committing.

## Self-service onboarding (future)
1. User pastes a URL; catalog check (same site and language → subscribe).
2. Live robots check and reachability; refuse if disallowed, with a clear message.
3. Run the investigation above.
4. **Preview:** show the last ~10 detected articles; the user confirms or flags.
5. Save to the shared catalog; start polling.

Needs: per-user limits, abuse prevention, a "can't be supported" message, human review rules.
