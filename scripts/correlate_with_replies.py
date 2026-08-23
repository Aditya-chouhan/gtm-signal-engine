#!/usr/bin/env python3
"""Correlate this engine's composite signal score against real reply rates.

THIS SCRIPT IS BLOCKED AS OF 2026-08-23. It requires a CSV of real reply
outcomes per entity, produced by artifact 5 (sequencing infrastructure),
which does not exist yet -- see plan artifact 5 status in
career/now.md. Running it without that input fails loudly on purpose
rather than falling back to synthetic replies, which would silently
recreate exactly the circular-metric problem this whole plan exists to
retire (see feedback_circular_validation in the vault: "a cost metric is
not a performance metric").

Usage once real data exists:
    python scripts/correlate_with_replies.py output/scored-entities-<date>.csv path/to/real_replies.csv

The replies CSV must have columns: ticker,reply_rate (0-1) or
ticker,replied (0/1) for at least 2 entities with non-identical values, or
the correlation is undefined (see signal_engine.correlation.spearman,
which returns None rather than a misleading 0.0 in that case) and this
script will say so rather than print a number.
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from signal_engine.correlation import spearman  # noqa: E402


def load_scores(path: Path) -> dict:
    with open(path, newline="") as f:
        return {row["ticker"]: float(row["composite_score"]) for row in csv.DictReader(f)}


def load_replies(path: Path) -> dict:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for row in rows:
        if "reply_rate" in row:
            out[row["ticker"]] = float(row["reply_rate"])
        elif "replied" in row:
            out[row["ticker"]] = float(row["replied"])
        else:
            raise ValueError("replies CSV must have a 'reply_rate' or 'replied' column")
    return out


def main():
    if len(sys.argv) != 3:
        print("Usage: correlate_with_replies.py <scored-entities.csv> <real_replies.csv>", file=sys.stderr)
        return 2

    scores_path, replies_path = Path(sys.argv[1]), Path(sys.argv[2])
    if not replies_path.exists():
        print(
            "BLOCKED: no real reply data exists yet. This script requires artifact 5 "
            "(sequencing infrastructure) to produce real sends/replies before it can run "
            "for real. Refusing to proceed with a synthetic stand-in -- see this script's "
            "module docstring for why.",
            file=sys.stderr,
        )
        return 1

    scores = load_scores(scores_path)
    replies = load_replies(replies_path)
    common = sorted(set(scores) & set(replies))
    if len(common) < 2:
        print(f"Only {len(common)} entities present in both files -- not enough to correlate.", file=sys.stderr)
        return 1

    xs = [scores[t] for t in common]
    ys = [replies[t] for t in common]
    rho = spearman(xs, ys)

    print(f"n = {len(common)} entities")
    if rho is None:
        print("Spearman's rho: undefined (see signal_engine.correlation.spearman docstring for why)")
    else:
        print(f"Spearman's rho: {rho:.3f}")
        print("A holdout of entities the engine scored low should be checked separately -- "
              "see the plan's artifact 7 verification requirement ('holdout included').")
    return 0


if __name__ == "__main__":
    sys.exit(main())
