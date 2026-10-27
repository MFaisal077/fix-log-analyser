"""
FIX log analyser: a daily health check of a FIX log, the way a support
analyst would run it.

Usage:
    python analyse.py data/sample_fix.log                    full report
    python analyse.py data/sample_fix.log --firm FIRM2       one firm only
    python analyse.py data/sample_fix.log --trace FIRM3-0002 one order's history
    python analyse.py data/sample_fix.log --csv rejects.csv  also save rejects to CSV
"""

import argparse
import csv
from collections import Counter

import checks
from fixlog import EXEC_TYPES, MSG_TYPES, firm_of, load_messages


def heading(title):
    print(f"\n{title}\n{'-' * len(title)}")


def describe(m):
    """One readable line for a message."""
    kind = MSG_TYPES.get(m.get("35"), m.get("35"))
    if m.get("35") == "8":
        kind += f" ({EXEC_TYPES.get(m.get('150'), m.get('150'))})"
    detail = f"{m.get('11', '')} {m.get('55', '')}"
    if m.get("32") not in (None, "0"):
        detail += f" filled {m['32']} @ {m['31']}"
    if "58" in m:
        detail += f' "{m["58"]}"'
    return f"{m['time']} {m['dir']:<3} {firm_of(m):<6} {kind:<36} {detail}"


def summary(messages):
    heading("Summary")
    print(f"Messages: {len(messages)}")
    for msg_type, n in Counter(m.get("35") for m in messages).most_common():
        print(f"  {MSG_TYPES.get(msg_type, msg_type):<26} {n}")

    orders = Counter(firm_of(m) for m in messages if m.get("35") == "D")
    filled = Counter()
    for m in messages:
        if m.get("35") == "8" and m.get("150") in ("1", "2"):
            filled[firm_of(m)] += int(m["32"])
    print("\nOrders and shares filled per firm:")
    for firm in sorted(orders):
        print(f"  {firm:<6} {orders[firm]:>3} orders  {filled[firm]:>7} shares")


def report_rejects(messages, csv_path=None):
    heading("Rejected orders (35=8, 150=8)")
    rejects = checks.rejected_orders(messages)
    if not rejects:
        print("None")
        return
    for (firm, reason), n in checks.reject_counts(messages).most_common():
        print(f"  {firm:<6} {n:>2} x {reason}")
    for m in rejects:
        print("  " + describe(m))

    if csv_path:
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "firm", "clordid", "symbol", "reason"])
            for m in rejects:
                writer.writerow([m["time"], firm_of(m), m.get("11"), m.get("55"), m.get("58")])
        print(f"  Saved {len(rejects)} rejects to {csv_path}")


def report_problems(messages):
    heading("Cancel rejects (35=9)")
    found = checks.cancel_rejects(messages)
    for m in found:
        print(f"  {describe(m)} (cancel of {m.get('41')})")
    if not found:
        print("None")

    heading("Quantity check: CumQty + LeavesQty = OrderQty")
    found = checks.quantity_mismatches(messages)
    for m, cum, leaves, qty in found:
        print(f"  {m['time']} {m.get('11')}: {cum} + {leaves} = {cum + leaves}, "
              f"but OrderQty is {qty}")
    if not found:
        print("OK")

    heading("Sequence numbers (34)")
    found = checks.sequence_gaps(messages)
    for m, (sender, target), expected, got in found:
        print(f"  {m['time']} {sender} -> {target}: expected {expected}, got {got} "
              f"({got - expected} message(s) missing)")
    if not found:
        print("OK")

    heading("Checksums (10)")
    found = checks.bad_checksums(messages)
    for m, expected in found:
        print(f"  {m['time']} {m.get('11', '')}: CheckSum {m.get('10')}, "
              f"should be {expected}")
    if not found:
        print("OK")


def main():
    parser = argparse.ArgumentParser(description="Health check for a FIX 4.2 log")
    parser.add_argument("logfile")
    parser.add_argument("--firm", help="only look at one firm, e.g. FIRM2")
    parser.add_argument("--trace", metavar="CLORDID", help="show one order's history")
    parser.add_argument("--csv", metavar="FILE", help="save rejected orders to a CSV file")
    args = parser.parse_args()

    messages = load_messages(args.logfile)

    if args.trace:
        heading(f"History of {args.trace}")
        for m in checks.trace_order(messages, args.trace):
            print("  " + describe(m))
        return

    if args.firm:
        messages = [m for m in messages if firm_of(m) == args.firm]

    summary(messages)
    report_rejects(messages, args.csv)
    report_problems(messages)


if __name__ == "__main__":
    main()
