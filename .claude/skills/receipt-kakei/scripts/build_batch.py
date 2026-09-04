#!/usr/bin/env python3
"""Turn parsed receipts into パシャ家計 transaction documents + write_db batches.

Usage:
    python3 build_batch.py receipts.json --out-dir /path/to/scratchpad

Input JSON — a list of receipts:

    [{"store": "業務スーパー 谷山店",
      "date": "2026-09-04",
      "total": 5080,                     # printed 合計; optional but checked
      "items": [{"name": "国産塩さば切身", "amount": 238, "category": "food"},
                ...]}]

Writes <out-dir>/docs/<doc_id>.json (one document each) and
<out-dir>/batch_NN.json (batch entries, <=50 per file, ready to paste into the
Artifact tool's `writes` parameter). Exits non-zero if a receipt's items do not
sum to its printed total — do not write unbalanced receipts.
"""

import argparse
import json
import os
import sys
from collections import Counter

VALID_EXPENSE = {
    "food", "daily", "clothing", "beauty", "social", "medical", "education",
    "utility", "transport", "communication", "housing", "hobby", "alcohol",
    "pet", "other",
}
VALID_INCOME = {"salary", "side", "allowance", "other_income"}
BATCH_MAX = 50


def build(receipts, out_dir, created_at, extra_categories=()):
    docs_dir = os.path.join(out_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    allowed = VALID_EXPENSE | VALID_INCOME | set(extra_categories)

    problems, entries, per_receipt = [], [], []

    for r in receipts:
        store = r["store"]
        date = r["date"]
        items = r["items"]
        subtotal = sum(int(i["amount"]) for i in items)

        printed = r.get("total")
        if printed is not None and int(printed) != subtotal:
            problems.append(
                "%s %s: items sum to %d but 合計 is %d (diff %+d) — check for a "
                "missed 割引 line or a double-counted quantity line"
                % (date, store, subtotal, int(printed), subtotal - int(printed))
            )

        for i in items:
            if i["category"] not in allowed:
                problems.append(
                    "%s %s: unknown category %r on %r"
                    % (date, store, i["category"], i["name"])
                )
            if int(i["amount"]) <= 0:
                problems.append(
                    "%s %s: non-positive amount on %r" % (date, store, i["name"])
                )

        receipt_id = "rcpt-%s%d" % (date.replace("-", ""), subtotal)
        for n, i in enumerate(items, 1):
            doc_id = "%s-%02d" % (receipt_id, n)
            doc = {
                "type": r.get("type", "expense"),
                "date": date,
                "yearMonth": date[:7],
                "category": i["category"],
                "amount": int(i["amount"]),
                "memo": i["name"],
                "store": store,
                "receiptId": receipt_id,
                "source": "receipt",
                "createdAt": created_at,
            }
            path = os.path.join(docs_dir, doc_id + ".json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False)
            entries.append({
                "op": "set",
                "collection": "transactions",
                "doc_id": doc_id,
                "file_path": os.path.abspath(path),
            })
        per_receipt.append((date, store, receipt_id, len(items), subtotal))

    if problems:
        print("REFUSING TO BUILD — fix these first:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return None

    batches = [entries[i:i + BATCH_MAX] for i in range(0, len(entries), BATCH_MAX)]
    for n, b in enumerate(batches, 1):
        with open(os.path.join(out_dir, "batch_%02d.json" % n), "w",
                  encoding="utf-8") as fh:
            json.dump(b, fh, ensure_ascii=False, indent=0)

    by_cat = Counter()
    amt_cat = Counter()
    for r in receipts:
        for i in r["items"]:
            by_cat[i["category"]] += 1
            amt_cat[i["category"]] += int(i["amount"])

    print("receipts: %d   items: %d   total: ¥%d"
          % (len(receipts), len(entries), sum(amt_cat.values())))
    for date, store, rid, n, s in per_receipt:
        print("  %s  %-24s %3d items  ¥%-7d  %s" % (date, store, n, s, rid))
    print("by category:")
    for c in sorted(amt_cat, key=lambda x: -amt_cat[x]):
        print("  %-14s %3d items  ¥%d" % (c, by_cat[c], amt_cat[c]))
    print("batches written: %s"
          % ", ".join("batch_%02d.json (%d)" % (n, len(b))
                      for n, b in enumerate(batches, 1)))
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("receipts")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--created-at", default=None,
                    help="ISO timestamp for createdAt (default: now, UTC)")
    ap.add_argument("--extra-categories", default="",
                    help="comma-separated custom category ids from settings/categories")
    args = ap.parse_args()

    created_at = args.created_at
    if not created_at:
        import datetime
        created_at = (datetime.datetime.now(datetime.timezone.utc)
                      .isoformat(timespec="milliseconds").replace("+00:00", "Z"))

    with open(args.receipts, encoding="utf-8") as fh:
        receipts = json.load(fh)

    extra = [c.strip() for c in args.extra_categories.split(",") if c.strip()]
    ok = build(receipts, args.out_dir, created_at, extra)
    sys.exit(0 if ok is not None else 1)


if __name__ == "__main__":
    main()
