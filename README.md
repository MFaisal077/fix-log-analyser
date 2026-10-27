# FIX Log Analyser

A small toolkit for the checks an application support analyst runs on a FIX 4.2 trading log: finding rejected orders, tracing one order's history, reconciling quantities, and spotting sequence-number gaps and corrupted messages. It covers the same job three ways, the way support work is actually done: **Bash** for the first quick look, **Python** for a repeatable report, and **SQL** for questions across the whole day.

All data is **synthetic**. `generate_sample_log.py` creates a made-up trading day between four firms (FIRM1–FIRM4) and a venue (EXCH), with a few problems planted on purpose for the analyser to find. Nothing comes from a real venue.

Only the Python standard library is used, so there's nothing to install.

## Quick start

```bash
python generate_sample_log.py              # writes data/sample_fix.log
python analyse.py data/sample_fix.log      # full health-check report
```

Other options:

```bash
python analyse.py data/sample_fix.log --firm FIRM2          # one firm only
python analyse.py data/sample_fix.log --trace FIRM3-0002    # one order's full history
python analyse.py data/sample_fix.log --csv rejects.csv     # also save rejects to CSV
bash one_liners.sh data/sample_fix.log                      # the same checks with grep/awk
python load_to_sqlite.py data/sample_fix.log                # load into fix.db
sqlite3 fix.db < queries.sql                                # run the SQL checks
python -m unittest discover tests                           # run the tests
```

## What it checks

| Check | FIX tags | What a problem means |
| --- | --- | --- |
| Rejected orders, counted by firm and reason | 35=8, 150=8, 58 | A firm's system may be sending badly formed orders |
| Cancel rejects | 35=9, 41, 434, 58 | A firm tried to cancel an order that had already filled |
| Quantity reconciliation | 14 + 151 = 38 | Filled plus open shares should always equal the order size |
| Sequence gaps on each session | 34, 49, 56 | Messages were lost and a resend would be needed |
| Checksums | 10 | A message was corrupted in transit |
| Order trace | 11, 41, 37 | Follows an order through its fills and any cancel request |

## Example report

The planted problems, as the analyser reports them:

```
Rejected orders (35=8, 150=8)
-----------------------------
  FIRM2   5 x Invalid quantity
  FIRM2   2 x Price required
  FIRM2   2 x Unknown security
  ...

Cancel rejects (35=9)
---------------------
  08:12:22.401 OUT FIRM3  OrderCancelReject     FIRM3-C0002  "Too late to cancel" (cancel of FIRM3-0002)

Quantity check: CumQty + LeavesQty = OrderQty
---------------------------------------------
  09:28:52.629 FIRM4-0002: 100 + 1400 = 1500, but OrderQty is 500

Sequence numbers (34)
---------------------
  10:07:28.689 EXCH -> FIRM3: expected 17, got 20 (3 message(s) missing)

Checksums (10)
--------------
  10:44:21.160 FIRM3-0010: CheckSum 007, should be 000
```

All nine rejects come from FIRM2, which points to a problem on FIRM2's side rather than the venue's. That's the kind of pattern a support analyst would raise with the firm.

Tracing one order (`--trace FIRM3-0002`) shows why its cancel failed: the order filled two seconds before the cancel request arrived.

```
  08:12:16.941 IN  FIRM3  NewOrderSingle                FIRM3-0002 BARC
  08:12:16.942 OUT FIRM3  ExecutionReport (New)         FIRM3-0002 BARC
  08:12:20.227 OUT FIRM3  ExecutionReport (Fill)        FIRM3-0002 BARC filled 5000 @ 210.00
  08:12:22.400 IN  FIRM3  OrderCancelRequest            FIRM3-C0002 BARC
  08:12:22.401 OUT FIRM3  OrderCancelReject             FIRM3-C0002  "Too late to cancel"
```

## Project structure

```
generate_sample_log.py   builds the synthetic log, with planted problems
fixlog.py                reads a log line into a dictionary of tag -> value
checks.py                one function per check
analyse.py               command-line report built on the checks
load_to_sqlite.py        loads execution reports into a SQLite table
queries.sql              reject counts, traded value, reconciliation, final order states
one_liners.sh            grep / sort / uniq / awk versions of the quick checks
tests/test_checks.py     unit tests on small hand-written messages
```

## How it works

**Reading a line.** Each log line is a time, a direction (`IN` = received by the venue, `OUT` = sent by it) and a FIX message. `parse_line` splits the message on `|`, then splits each pair on the first `=` only, so text like `58=Price=0 not allowed` survives. The result is a dictionary such as `{"35": "D", "11": "FIRM1-0001", ...}`.

**Sequence numbers.** Every session direction (for example EXCH → FIRM3) has its own counter in tag 34, which must go up by exactly 1. The check keeps the last number seen for each `(sender, target)` pair and flags any jump.

**Checksums.** FIX tag 10 is the sum of every byte before it, mod 256. The log shows the separator as `|`, but the real separator is the invisible SOH character, so the check swaps it back before adding up.

**Order trace.** A cancel request has its own ClOrdID (11) but points back to the original order through OrigClOrdID (41), and every report about the order shares the venue's OrderID (37). The trace follows all three links.

## SQL checks

`queries.sql` answers whole-day questions against the `executions` table:

1. Firms with more than 2 rejects, and their reasons (`GROUP BY` + `HAVING`)
2. Traded shares and value per symbol
3. Reports where CumQty + LeavesQty ≠ OrderQty
4. Each order's final state, using `ROW_NUMBER()` to find the latest report per order
5. Orders still open at the end of the day, per firm

## Possible next steps

- Handle amend messages (35=G) and replaced orders (150=5)
- Read SOH-separated logs directly as well as `|`-separated ones
- Check heartbeats: flag a session that goes quiet for longer than its HeartBtInt (108)
