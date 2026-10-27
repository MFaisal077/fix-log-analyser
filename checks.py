"""
The checks a support analyst runs on a FIX log.

Each function takes the list of parsed messages and returns a list of
problems found (an empty list means everything looked fine).
"""

from collections import Counter

from fixlog import firm_of


def rejected_orders(messages):
    """Execution reports with ExecType 150=8: orders the venue refused."""
    return [m for m in messages if m.get("35") == "8" and m.get("150") == "8"]


def reject_counts(messages):
    """How many rejects each firm got, and for which reason."""
    return Counter((firm_of(m), m.get("58", "no reason given"))
                   for m in rejected_orders(messages))


def cancel_rejects(messages):
    """OrderCancelReject messages (35=9): a cancel or amend that failed."""
    return [m for m in messages if m.get("35") == "9"]


def quantity_mismatches(messages):
    """On every execution report, CumQty (14) + LeavesQty (151) should equal
    OrderQty (38). Rejected and cancelled orders are left out, because their
    LeavesQty is set to 0 on purpose."""
    problems = []
    for m in messages:
        if m.get("35") != "8" or m.get("150") in ("4", "8"):
            continue
        cum, leaves, qty = int(m["14"]), int(m["151"]), int(m["38"])
        if cum + leaves != qty:
            problems.append((m, cum, leaves, qty))
    return problems


def sequence_gaps(messages):
    """MsgSeqNum (34) must go up by exactly 1 on each session direction
    (e.g. EXCH -> FIRM3). A jump means messages were lost."""
    last_seen = {}   # (sender, target) -> last sequence number
    gaps = []
    for m in messages:
        session = (m.get("49"), m.get("56"))
        seq = int(m["34"])
        if session in last_seen and seq != last_seen[session] + 1:
            gaps.append((m, session, last_seen[session] + 1, seq))
        last_seen[session] = seq
    return gaps


def bad_checksums(messages):
    """FIX CheckSum (10) = the sum of every byte before "10=", mod 256.
    The real separator is SOH, so the "|" in the log is swapped back first."""
    problems = []
    for m in messages:
        raw = m["raw"].replace("|", "\x01")
        body, sep, rest = raw.rpartition("\x0110=")
        if not sep:
            continue
        expected = f"{sum((body + chr(1)).encode()) % 256:03d}"
        if m.get("10") != expected:
            problems.append((m, expected))
    return problems


def trace_order(messages, clordid):
    """Every message about one order: the order itself, its fills, and any
    cancel request that points back to it through OrigClOrdID (41)."""
    order_ids = {m.get("37") for m in messages if m.get("11") == clordid}
    order_ids.discard(None)
    order_ids.discard("NONE")
    return [m for m in messages
            if clordid in (m.get("11"), m.get("41")) or m.get("37") in order_ids]
