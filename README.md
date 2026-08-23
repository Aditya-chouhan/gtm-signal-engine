# GTM Signal Engine — Multi-Source Signal Fusion

A composite scoring engine that ingests real signals from three independent,
free, public APIs — SEC EDGAR filings, GitHub release activity, and Hacker
News mentions — resolves them to canonical entities, and combines them with
a documented Severity × Confidence × Recency model. No synthetic data
anywhere in this repo; every signal is a real, dereferenceable record from a
live API call.

> **What this is not.** This is not a real prospect list. The 14 entities
> below are large public SaaS companies, chosen for exactly one reason:
> verifiable coverage across all three signal sources (a real GitHub org, a
> real SEC CIK, a name worth searching on HN). They are not realistic
> outbound targets for a solo GTM consulting practice — using them as one
> would misrepresent who this engine would actually be pointed at in
> production. They exist purely so the fusion mechanism could be proven
> against real, independently-checkable data instead of invented records.

## Why this exists

The honest test this plan set for a signal engine was always: *correlate the
composite score against real reply rates, holdout included* — not "does the
scoring formula run." That test is **blocked** on artifact 5 (sequencing
infrastructure), which doesn't exist yet in this portfolio. Rather than wait
idle or fake the missing half, this repo builds and proves the half that
doesn't depend on it: real multi-source ingestion, real entity resolution,
a documented (not tuned-to-look-good) scoring model, and — because it
surfaced during a real run — real failure handling. See
`scripts/correlate_with_replies.py`, which refuses to run against synthetic
replies and says exactly what it's waiting on.

## The three sources, and why each is real

| Source | What it gives | Verified live | Confidence |
|---|---|---|---|
| SEC EDGAR full-text search (`efts.sec.gov`) | 8-K filings, keyed by CIK, ranked by which item they disclose | 2026-08-23 | 0.95 — CIK is unambiguous |
| GitHub REST + Search API | Release-cadence change for the org's highest-starred public repo | 2026-08-23 | 0.90 — org slug is unambiguous |
| HN Algolia Search API | Story mentions, severity = the story's own point count | 2026-08-23 | 0.60 — name-string matching, see below |

No API key for any of the three. SEC asks only for a descriptive
User-Agent (`sec_source.USER_AGENT`), which this repo sends.

## The scoring model — every constant explained, none tuned

`src/signal_engine/scoring.py` is the model; nothing in it is arbitrary:

- **Recency** is exponential decay, half-life 30 days — a signal exactly 30
  days old scores half of a fresh one, two half-lives a quarter. Chosen
  over linear decay because it never needs a hard cutoff.
- **SEC severity** comes from the filing's own disclosed 8-K item code —
  Item 1.03 (bankruptcy) ranks above Item 5.02 (officer departure) above
  Item 9.01 (exhibits only) — a rubric built from what SEC's own item
  definitions structurally imply, not invented.
- **GitHub severity** is the org's trailing-90-day release count *relative
  to its own prior-90-day window* — an absolute release count means
  nothing without a baseline; a percent-change-from-self does.
- **HN severity** is the story's real point count, capped at 100 — HN's own
  crowd-judged importance signal, not a proxy invented for this project.
- **Cross-source aggregation is noisy-OR** (`1 - Π(1 - sᵢ)`), not a sum
  and not a max — a plain sum would let ten weak HN mentions outscore one
  confirmed SEC bankruptcy filing; a plain max would throw away the one
  thing multi-source fusion is supposed to capture, that two independent
  sources corroborating the same entity is real additional evidence. The
  full reasoning is in the module docstring. **This rule has not been
  validated against real outcomes** — it's the documented starting point,
  not a proven one; that validation is exactly what
  `correlate_with_replies.py` is waiting to do.

## Entity resolution — the one place this can go wrong, and how it's handled

SEC and GitHub signals are keyed to an unambiguous identifier (CIK, org
slug) before a request is even made — there's nothing to resolve after the
fact. HN starts from free text, so `dedup.py` matches a story's title
against each entity's canonical name (whole-word, case-sensitive). If **zero
or more than one** entity matches, the hit is **dropped, not guessed** — a
two-company story doesn't get arbitrarily assigned to one of them.

## What broke on the first real run, and what that revealed

**SEC EDGAR 500'd on 3 of 14 entities mid-run (2026-08-23), confirmed
transient.** The exact failing request, re-issued by hand seconds later,
succeeded every time — this was SEC's search index under load, not a bug in
the request. The first run's script had no retry and would have silently
shipped an 11/14 dataset. Fixed with `retry.py` (bounded exponential
backoff, 3 attempts), applied to the SEC fetch path, and the run was
repeated clean. This is exactly the distinction the portfolio's n8n artifact
already proved for a different system: catching this required actually
running it against a live API repeatedly, not reasoning about failure modes
in the abstract.

**HN's search matches far more than titles, which drives a large,
name-dependent resolution-drop rate.** Inspecting Okta's zero-resolved run
by hand: Algolia's `query=Okta` returned real HN stories — "Auth0 Certified
Developer Exam Study Guide," "BreachForums logs reveal anonymizers of
choice" — where the literal word "Okta" never appears in the title at all,
meaning the match came from body text, URL, or comments. Passing
`restrictSearchableAttributes=title` did not change this. The consequence:
short or common company names (Okta, Twilio, Asana) get a much higher
resolution-drop rate than distinctive ones (Cloudflare, GitLab), **not
because those companies are less newsworthy, but because Algolia's search
surface is broader than the field this engine actually checks.** The
conservative choice — resolve only on a literal title match, drop
everything else rather than guess from body text a company is only
incidentally mentioned in — was kept deliberately: solving this properly
needs real entity disambiguation (NLP), which is out of scope here and
would be inventing precision this repo doesn't have. The real, measured
drop rates are reported per-entity in `output/fetch-log-*.json`, not
averaged away.

## Verified run — 2026-08-23, clean, zero errors

456 signals across 14/14 entities, zero fetch failures logged
(`output/fetch-log-2026-08-23.json`). Top and bottom of the ranked table:

| Rank | Ticker | Composite | Signals (SEC / GitHub / HN) |
|---|---|---|---|
| 1 | NET (Cloudflare) | 1.0000 | 18 / 1 / 51 |
| 2 | SNOW (Snowflake) | 0.9039 | 8 / 1 / 35 |
| 3 | MNDY (monday.com) | 0.8983 | 0 / 1 / 0 — one high-severity GitHub signal alone |
| … | | | |
| 12 | MDB (MongoDB) | 0.4165 | 7 / 0 / 38 |
| 13 | CRWD (CrowdStrike) | 0.3137 | 10 / 0 / 3 |

Full table: `output/scored-entities-2026-08-23.csv`. Raw per-signal evidence
(every SEC filing URL, GitHub releases page, HN story link) in
`output/all-signals-2026-08-23.json`.

This run is the third attempt, not the first — see "What broke" above. The
first attempt lost 3/14 entities to a bare SEC 500; the second lost most of
the GitHub and HN passes to transient connection resets; this one, with
`retry.py` wrapping all three sources, came back clean. All three runs'
raw logs are described in this README rather than only the clean one, since
citing just the run that worked would hide exactly the resilience work that
made it reproducible.

## Reproduce it

```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/pytest -q                        # 44 tests, offline, against committed fixtures
./.venv/bin/python scripts/fetch_live_signals.py   # real live run, ~3-4 min (GitHub Search paces at 10/min)
```

Committed fixtures in `fixtures/` (real API responses captured 2026-08-23)
let the test suite run fully offline; `scripts/fetch_live_signals.py` is the
only thing that touches the network, and it's what produced every file in
`output/`.

## What this doesn't prove

- **The scoring model is unvalidated.** Severity rubrics and the noisy-OR
  aggregation are documented, defensible starting points — not measured
  against any real outcome. `correlate_with_replies.py` is built and ready;
  it has never run against real data because artifact 5 doesn't exist yet.
- **This is not a prospect list** — see the warning at the top.
- **HN resolution is conservative by design**, which means real recall loss
  on common/short company names — quantified per-entity in the fetch log,
  not hidden.
- **One SEC 500 incident, observed once.** The retry fix is real and
  tested, but this is one data point on SEC's reliability, not a
  statistically established failure rate.

## Files

```
src/signal_engine/entities.py      canonical entity list — real tickers/CIKs/GitHub orgs
src/signal_engine/scoring.py       Signal dataclass, severity rubrics, decay, noisy-OR aggregation
src/signal_engine/dedup.py         HN title -> canonical ticker resolution, ambiguity handling
src/signal_engine/retry.py         bounded exponential backoff (added after a real SEC 500)
src/signal_engine/correlation.py   Spearman rho, stdlib only — the math correlate_with_replies.py needs
src/signal_engine/engine.py        aggregates Signals into a ranked entity table
src/signal_engine/sources/         one module per API (sec_source, github_source, hn_source)
scripts/fetch_live_signals.py      the only network-touching script; produces everything in output/
scripts/correlate_with_replies.py  blocked on artifact 5 -- fails loudly, on purpose, until real reply data exists
fixtures/                          real API responses, captured 2026-08-23, used for offline tests
output/                            real committed run output -- scored table, raw signals, fetch log
tests/                             44 tests: scoring math, dedup, retry, correlation math, and fixture-parsing
```
