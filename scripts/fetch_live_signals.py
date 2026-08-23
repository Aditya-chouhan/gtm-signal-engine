#!/usr/bin/env python3
"""Hit all three real APIs for all 14 entities, build the composite scored
table, and write everything -- raw responses included -- to output/, so the
result is regenerable and auditable rather than asserted.

Takes a few minutes: GitHub Search is rate-limited to 10/min unauthenticated,
so the GitHub pass alone paces at ~6.5s/entity by design (see
sources/github_source.py). SEC and HN are comfortably faster.
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from signal_engine.entities import ENTITIES  # noqa: E402
from signal_engine.engine import build_entity_table  # noqa: E402
from signal_engine.sources import sec_source, github_source, hn_source  # noqa: E402

HALF_LIFE_DAYS = 30
WINDOW_DAYS = 180


def main():
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")

    all_signals = []
    raw_log = {"captured_at": now.isoformat(), "sec": {}, "github": {}, "hn": {}}
    hn_drop_stats = {}

    print(f"Fetching real signals for {len(ENTITIES)} entities, window {start_date}..{end_date}")

    for e in ENTITIES:
        print(f"  [sec]    {e.ticker} (CIK {e.cik})", flush=True)
        try:
            sigs = sec_source.fetch_signals_for_entity(e.ticker, e.cik, start_date, end_date)
            all_signals.extend(sigs)
            raw_log["sec"][e.ticker] = {"filing_signals": len(sigs)}
        except Exception as exc:
            print(f"    SEC fetch failed for {e.ticker}: {exc}", file=sys.stderr)
            raw_log["sec"][e.ticker] = {"error": str(exc)}

    for e in ENTITIES:
        print(f"  [github] {e.ticker} (org {e.github_org})", flush=True)
        try:
            sig = github_source.fetch_signal_for_entity(e.ticker, e.github_org)
            if sig is not None:
                all_signals.append(sig)
            raw_log["github"][e.ticker] = {
                "signal_emitted": sig is not None,
                "event_type": sig.event_type if sig else None,
            }
        except Exception as exc:
            print(f"    GitHub fetch failed for {e.ticker}: {exc}", file=sys.stderr)
            raw_log["github"][e.ticker] = {"error": str(exc)}
        time.sleep(0.5)  # stay well clear of the 60/hr core-API ceiling too

    for e in ENTITIES:
        print(f"  [hn]     {e.ticker} (query: {e.hn_aliases[0]!r})", flush=True)
        try:
            sigs, stats = hn_source.fetch_signals_for_query(e.hn_aliases[0], days_back=WINDOW_DAYS)
            all_signals.extend(sigs)
            hn_drop_stats[e.ticker] = stats
            raw_log["hn"][e.ticker] = stats
        except Exception as exc:
            print(f"    HN fetch failed for {e.ticker}: {exc}", file=sys.stderr)
            raw_log["hn"][e.ticker] = {"error": str(exc)}
        time.sleep(0.3)

    results = build_entity_table(all_signals, half_life_days=HALF_LIFE_DAYS, now=now)

    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    run_date = now.strftime("%Y-%m-%d")

    scored_path = out_dir / f"scored-entities-{run_date}.csv"
    with open(scored_path, "w") as f:
        f.write("rank,ticker,name,composite_score,signal_count,sec_signals,github_signals,hn_signals\n")
        for i, r in enumerate(results, start=1):
            f.write(f"{i},{r.ticker},{r.name},{r.composite_score:.4f},{r.signal_count},"
                     f"{r.by_source.get('sec', 0)},{r.by_source.get('github', 0)},{r.by_source.get('hn', 0)}\n")

    raw_path = out_dir / f"fetch-log-{run_date}.json"
    with open(raw_path, "w") as f:
        json.dump(raw_log, f, indent=2)

    all_signals_path = out_dir / f"all-signals-{run_date}.json"
    with open(all_signals_path, "w") as f:
        json.dump([
            {
                "ticker": s.ticker, "source": s.source, "event_type": s.event_type,
                "severity": s.severity, "confidence": s.confidence,
                "observed_at": s.observed_at.isoformat(), "evidence_url": s.evidence_url,
            }
            for s in all_signals
        ], f, indent=2)

    total_hn_hits = sum(v.get("hits_returned", 0) for v in hn_drop_stats.values())
    total_hn_dropped = sum(v.get("dropped", 0) for v in hn_drop_stats.values())
    print(f"\nDone. {len(all_signals)} total signals across {len(ENTITIES)} entities.")
    if total_hn_hits:
        drop_pct = total_hn_dropped / total_hn_hits * 100
        print(f"HN: {total_hn_hits} hits returned, {total_hn_dropped} dropped on entity "
              f"resolution ({drop_pct:.0f}%)")
    else:
        print("HN: no hits returned")
    print(f"Wrote {scored_path.relative_to(ROOT)}, {raw_path.relative_to(ROOT)}, {all_signals_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
