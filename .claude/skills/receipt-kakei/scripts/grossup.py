#!/usr/bin/env python3
"""Convert a 外税 (tax-exclusive) receipt into tax-inclusive item amounts.

On a 外税 receipt the item lines are pre-tax and the printed 合計 adds the tax
at the bottom, so writing the lines as-is under-records what was actually paid.
This grosses each line up so that each tax band lands exactly on the band total
the receipt itself prints (税率8%対象額 / 税率10%対象額), using largest-remainder
rounding — no yen is invented or lost.

Usage:
    python3 grossup.py exclusive.json > receipts.json

Input — one or more receipts whose items carry a `rate` (8 or 10) and a
pre-tax `amount` (already net of any 割引), plus the printed band totals:

    [{"store": "タイヨー慈眼寺店",
      "date": "2026-09-02",
      "total": 3021,                       # printed 合計 (tax-inclusive)
      "bands": {"8": 2724, "10": 297},     # printed 税率N%対象額
      "items": [{"name": "千切りキャベツ", "amount": 98,
                 "rate": 8, "category": "food"}, ...]}]

Output is the ordinary receipts format (tax-inclusive `amount`, no `rate`),
ready for build_batch.py. Exits non-zero if the bands do not reconcile.
"""

import json
import sys
from collections import defaultdict


def grossup(receipt):
    """Return (items, problems) with tax-inclusive amounts."""
    problems = []
    bands = {int(k): int(v) for k, v in receipt["bands"].items()}

    by_rate = defaultdict(list)
    for i in receipt["items"]:
        by_rate[int(i["rate"])].append(i)

    if set(by_rate) != set(bands):
        problems.append(
            "%s %s: item rates %s do not match the printed bands %s"
            % (receipt["date"], receipt["store"],
               sorted(by_rate), sorted(bands))
        )
        return [], problems

    if sum(bands.values()) != int(receipt["total"]):
        problems.append(
            "%s %s: bands sum to %d but 合計 is %d"
            % (receipt["date"], receipt["store"],
               sum(bands.values()), int(receipt["total"]))
        )

    out = []
    for rate, items in by_rate.items():
        pre = sum(int(i["amount"]) for i in items)
        target = bands[rate]
        expected = pre + pre * rate // 100
        if abs(expected - target) > 1:
            problems.append(
                "%s %s: %d%% lines total %d pre-tax, which grosses to about %d, "
                "but the receipt prints %d — a line is missing or misread"
                % (receipt["date"], receipt["store"], rate, pre, expected, target)
            )

        # Largest-remainder: floor each share, then hand the leftover yen to the
        # lines with the biggest discarded fraction.
        scaled = [int(i["amount"]) * target for i in items]
        floors = [s // pre for s in scaled]
        rema = [s % pre for s in scaled]
        leftover = target - sum(floors)
        order = sorted(range(len(items)), key=lambda n: (-rema[n], n))
        for n in order[:leftover]:
            floors[n] += 1

        for i, amount in zip(items, floors):
            out.append({"name": i["name"], "amount": amount,
                        "category": i["category"]})

    return out, problems


def main():
    with open(sys.argv[1], encoding="utf-8") as fh:
        receipts = json.load(fh)

    result, problems = [], []
    for r in receipts:
        items, probs = grossup(r)
        problems += probs
        result.append({"store": r["store"], "date": r["date"],
                       "total": int(r["total"]), "items": items})
        if items:
            print("%s %s: %d items, %d → %d (tax %+d)"
                  % (r["date"], r["store"], len(items),
                     sum(int(i["amount"]) for i in r["items"]),
                     sum(i["amount"] for i in items),
                     sum(i["amount"] for i in items)
                     - sum(int(i["amount"]) for i in r["items"])),
                  file=sys.stderr)

    if problems:
        print("REFUSING — fix these first:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        sys.exit(1)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
