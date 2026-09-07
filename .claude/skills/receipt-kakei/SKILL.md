---
name: receipt-kakei
description: Read Japanese supermarket/drugstore receipt photos, split them into line items, categorize each item, and write them straight into the パシャ家計 budget app's artifact database. Use whenever the user sends receipt photos (レシート), asks to record spending into 家計簿/パシャ家計, or asks to check what is already recorded there.
---

# パシャ家計 — レシート取り込み

Turn receipt photos into categorized expense rows in the パシャ家計 app's
database. Read the photo here in the conversation and write the rows with the
`Artifact` tool — the user does not copy, paste, or retype anything.

## The app

| | |
|---|---|
| Artifact | https://claude.ai/code/artifact/bcc8e2fc-5b86-4d76-83d3-a8aaf0c561a4 |
| Source | `pasha-kakei.html` (published from a scratchpad; re-read the artifact if you need the current code) |
| Collection | `transactions` |
| Settings doc | `settings/categories` — `{hiddenCategoryIds, customCategories}` |

The app subscribes to `transactions` with `onSnapshot`, so rows appear on the
user's phone the moment the write commits. No republish, no reload.

## Document shape

Every row is one **item**, not one receipt. Write exactly these fields — the
app's calendar and report tabs read all of them:

```json
{
  "type": "expense",
  "date": "2026-09-04",
  "yearMonth": "2026-09",
  "category": "food",
  "amount": 5080,
  "memo": "国産塩さば切身",
  "store": "業務スーパー 谷山店",
  "receiptId": "rcpt-20260904-5080",
  "source": "receipt",
  "createdAt": "2026-09-04T00:00:00.000Z"
}
```

- `amount` — integer yen, no commas, **after** any discount.
- `memo` — the item name as printed, even if the receipt truncates it
  (`やわらか卵のシフ` stays as-is; do not guess the full word).
- `yearMonth` — must be `date[:7]`; the report tab groups on it.
- `receiptId` — same value for every item off one receipt, so a receipt can be
  found and removed as a unit.
- `source` — `"receipt"` here; the app writes `"manual"` for typed entries.

## Category IDs

Use the `id`, never the Japanese label:

`food` 食料品 · `daily` 日用品 · `clothing` 衣服 · `beauty` 美容 ·
`social` 交際費 · `medical` 医療費 · `education` 教育費 · `utility` 光熱費 ·
`transport` 交通費 · `communication` 通信費 · `housing` 住居費 ·
`hobby` 趣味・娯楽 · `alcohol` 酒・アルコール · `pet` ペット用品 · `other` その他

Income rows use `type:"income"` with `salary` / `side` / `allowance` /
`other_income`.

Before assigning, check `settings/categories` for `customCategories` the user
added and `hiddenCategoryIds` they turned off — do not assign a hidden one.

## Reading rules

These come from real receipts that were misread before. Follow them exactly.

**1. Discount lines fold into the item above.** `割引` / `値引` is never its own
row — subtract it from the preceding item.

> `国産塩さば切身 ¥298` then `割引20% -60` → one row, `国産塩さば切身`, **238**.

**2. Quantity lines are already totaled.** A line like `(3個 x @88)` restates
the line above; the amount printed on the item line is the total. Emit one row
at that amount, and drop the quantity line.

**3. Skip the footer.** 小計 / 合計 / 外税額 / 内消費税 / 買上点数 / お預り /
お釣り / クレジット / card numbers / 登録番号 / 電話番号 are never items.

**4. 外税 receipts must be grossed up.** Check the footer before trusting the
item prices:

- **内税** (item prices tax-included) — the item lines sum to 合計. Write them
  as printed.
- **外税** (tax added at the bottom) — the item lines sum to **小計**, and
  合計 = 小計 + 外税額. Writing the printed prices under-records what was
  actually paid.

**Decide this from the footer of the receipt in front of you, never from the
store name.** A `小計` that differs from `合計` means 外税, full stop; a footer
that says `税込小計` is stating 内税 outright. Observed so far: タイヨー and
業務スーパー print 外税 (業務スーパー 谷山店, 2026-09-07: 小計 ¥5,396 → 合計
¥5,846), ダイレックス prints 内税 (2026-09-03: 税込小計 17品 ¥4,737 = 合計).
Chains are not a reliable predictor — read the footer every time.

The cheapest confirmation is the tax bands: each band total on a correct
import equals the receipt's own `(税率N%対象額)`. The 09-03 and 09-04 imports
were re-checked against the paper receipts this way and both matched exactly.

For 外税, gross each line up so every tax band lands exactly on the band total
the receipt already prints as `(税率8%対象額)` / `(税率10%対象額)` — those two
figures sum to 合計, so they are the target, not something to compute.
`scripts/grossup.py` does this with largest-remainder rounding.

> タイヨー慈眼寺店 2026-09-02: 小計 ¥2,793 → 合計 ¥3,021. The 8% lines
> (¥2,523 pre-tax) became ¥2,724 and the 10% lines (¥270) became ¥297.

**5. The tax mark is evidence, not decoration.** This is the single most
reliable signal on a Japanese receipt:

| Mark | Rate | Means |
|---|---|---|
| `外8` `内8` `◆` `※` | 8% 軽減税率 | food & drink for people → `food` |
| `外10` or no mark | 10% | not human food → `alcohol` / `daily` / `pet` / `beauty` / stationery |

A line that *looks* like food but carries no 8% mark is usually pet food. On a
real receipt `コンボD もっちりチキン ¥679×3` read as chicken deli — but it was
10%-taxed, and the footer's `10%対象 ¥2,166` equalled `679×3 + 129`, proving it
was pet food (コンボ is 日本ペットフード). **Reconcile the tax subtotals; they
settle these cases.**

**6. Name keywords, after the tax check:**

- チューハイ / 氷結 / -196 / ビール / ハイボール / 日本酒 / 焼酎 → `alcohol`
- コンボ / シーバ / モンプチ / いなば / ちゅ〜る / 猫砂 / ペットシーツ → `pet`
- 洗剤 / シャンプー / ティッシュ / 電池 / クリップ / 鏡 → `daily`
- 薬 / 絆創膏 / マスク / サプリ / 湿布 → `medical`
- everything else edible → `food`

**When the name is unreadable and nothing identifies it, use `food`** — even on
a 10% line. The user's standing instruction: 「私も分からないけど、食品に入れ
といて」. Reserve `other` for items you *can* identify as non-food but that fit
no category. Say in your report which items landed in `food` this way, so the
user can correct them in the app.

The tax mark still decides anything you *can* name — an unmarked コンボ or 氷結
is pet food or alcohol, not food. This fallback is only for genuine unknowns,
like `鹿児島市岡之原` (2026-09-02, ¥110 / ¥187, 外10, product code 3712 twice —
possibly 鹿児島市指定ごみ袋, never confirmed).

Keep alcohol out of `food` — mixing them inflates the 食費 line the user
actually watches.

## Procedure

1. **Read the photo.** If the print is too small, say so and ask for a tighter
   shot of the item list rather than guessing amounts.

2. **Check for a duplicate before writing.** Read the collection and look for
   the same `store` + `date` + total. This check — not the document id — is
   what prevents double-importing.

   ```
   Artifact  action=read_db  url=<artifact>  db_op=list
             collection=transactions  query={"limit":1000}
             out_dir=<scratchpad>/verify
   ```

   Reading with `out_dir` saves each row to a file instead of dumping all of
   them into the conversation; sum them with a script.

3. **Balance the receipt before writing.** Sum your items and compare against
   the printed 合計 — on a 外税 receipt, first sum against 小計, then gross up
   per rule 4. They must match to the yen. If they do not, re-read: a mismatch
   is almost always a missed discount line, a double-counted quantity line, or
   an unnoticed 外税 footer. Never write rows that do not balance. 買上点数 is
   a free second check on your item count.

4. **Build the documents** with the scripts rather than typing them:
   `scripts/grossup.py` first if the receipt is 外税, then
   `scripts/build_batch.py`, which derives `yearMonth`, `receiptId`, and the
   ids. Both refuse to emit anything that does not reconcile.

5. **Write in batches** of at most 50:

   ```
   Artifact  action=write_db  url=<artifact>  db_op=batch
             writes=[{"op":"set","collection":"transactions",
                      "doc_id":"rcpt-20260904-5080-01",
                      "file_path":"<scratchpad>/docs/rcpt-20260904-5080-01.json"}, ...]
   ```

   `file_path` points at one JSON file per document, so Japanese item names are
   never retyped into a tool call. A batch commits atomically.

6. **Verify by reading back**, then report per-receipt and per-category totals.

Document ids go `rcpt-<YYYYMMDD><総額>-<NN>` — content-derived, so a re-import
of an identical receipt overwrites instead of duplicating. (The first import,
2026-09-01〜09-04, predates this and uses `rcpt-20260904-<n>-<NN>`; leave those
alone.)

## Removing a bad import

Delete by `receiptId` — read the collection, collect the ids sharing that
`receiptId`, and batch `{"op":"delete",...}` them. Do not ask the user to clear
rows by hand in the app.

## Reporting back

Give the user, in Japanese: per-receipt total, per-category breakdown, and an
explicit note on anything the tax marks decided (pet food, alcohol) or any item
you were unsure about. Confirm the totals matched the printed 合計.
