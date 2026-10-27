"""
Generate a synthetic FIX 4.2 trading-day log for testing the analyser.

Nothing here comes from a real venue: the firms (FIRM1-FIRM4), the venue
(EXCH), the order IDs and the market codes are all made up.

A few problems are planted on purpose so the analyser has something to find:
  - FIRM2 sends a lot of orders that get rejected
  - one cancel request is rejected (35=9)
  - one execution report where CumQty + LeavesQty does not equal OrderQty
  - a sequence-number gap on one session
  - one message with a wrong checksum

Run:  python generate_sample_log.py          (writes data/sample_fix.log)
"""

import os
import random

random.seed(42)  # same "random" day every time, so results are repeatable

SOH = "\x01"  # the real FIX field separator; logs usually show it as "|"
VENUE = "EXCH"
FIRMS = ["FIRM1", "FIRM2", "FIRM3", "FIRM4"]
PRICES = {"BARC": 210.00, "VOD": 72.50, "BP": 455.00, "AZN": 11780.00, "SHEL": 2650.00}
DATE = "20261021"

seq = {}            # next sequence number for each direction, e.g. ("FIRM1", "EXCH")
next_order_id = 500001
next_exec_id = 1
order_count = {f: 0 for f in FIRMS}
lines = []


def checksum(text):
    """FIX checksum: add up every byte, keep the remainder after dividing by 256."""
    return f"{sum(text.encode()) % 256:03d}"


def build(msg_type, sender, target, fields, bad_checksum=False):
    """Turn a list of (tag, value) pairs into one complete FIX message."""
    key = (sender, target)
    seq[key] = seq.get(key, 1)
    seq_num = seq[key]
    seq[key] += 1

    body = [("35", msg_type), ("34", seq_num), ("49", sender), ("56", target),
            ("52", f"{DATE}-{clock}")] + fields
    body_text = "".join(f"{tag}={value}{SOH}" for tag, value in body)
    head = f"8=FIX.4.2{SOH}9={len(body_text)}{SOH}"
    total = checksum(head + body_text)
    if bad_checksum:
        total = f"{(int(total) + 7) % 256:03d}"
    return head + body_text + f"10={total}{SOH}"


def log(direction, message):
    """Write one log line: time, IN/OUT, then the message with | separators."""
    lines.append(f"{clock} {direction:<3} {message.replace(SOH, '|')}")


def tick(min_s, max_s):
    """Move the clock forward by a random number of seconds."""
    global clock_s
    clock_s += random.uniform(min_s, max_s)
    set_clock()


def set_clock():
    global clock
    h, rem = divmod(clock_s, 3600)
    m, s = divmod(rem, 60)
    clock = f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def exec_report(firm, clordid, order_id, symbol, side, qty, price, exec_type,
                status, last_qty=0, last_px=0, cum=0, leaves=None, extra=None,
                bad_checksum=False):
    """Send an execution report (35=8) from the venue to a firm."""
    global next_exec_id
    if leaves is None:
        leaves = qty - cum
    avg = f"{price:.4f}" if cum else "0"
    fields = [("11", clordid), ("37", order_id), ("17", f"E{next_exec_id:06d}"),
              ("20", 0), ("150", exec_type), ("39", status), ("55", symbol),
              ("54", side), ("38", qty), ("40", 2)]
    if price:
        fields.append(("44", f"{price:.2f}"))
    fields += [("32", last_qty), ("31", f"{last_px:.2f}" if last_px else 0),
               ("14", cum), ("151", leaves), ("6", avg)]
    if last_qty:
        fields.append(("30", "XLIT"))
    fields += extra or []
    next_exec_id += 1
    log("OUT", build("8", VENUE, firm, fields, bad_checksum))


# ---------------------------------------------------------------- the day
clock_s = 7 * 3600 + 55 * 60  # 07:55
set_clock()

for firm in FIRMS:  # everyone logs on before the open
    log("IN", build("A", firm, VENUE, [("98", 0), ("108", 30)]))
    tick(0.001, 0.002)
    log("OUT", build("A", VENUE, firm, [("98", 0), ("108", 30)]))
    tick(5, 20)

clock_s = 8 * 3600
set_clock()
planted = {"qty_mismatch": False, "gap": False, "checksum": False, "cxl_reject": False}

for i in range(60):
    tick(30, 420)
    firm = random.choice(FIRMS)
    order_count[firm] += 1
    clordid = f"{firm}-{order_count[firm]:04d}"
    symbol = random.choice(list(PRICES))
    side = random.choice([1, 2])
    qty = random.choice([500, 1000, 2000, 3000, 5000])
    price = PRICES[symbol]

    # FIRM2's system has a bug: about half of its orders are badly formed
    if firm == "FIRM2" and random.random() < 0.5:
        problem = random.choice(["no_price", "no_price", "bad_symbol", "zero_qty"])
        fields = [("11", clordid), ("55", "XYZ" if problem == "bad_symbol" else symbol),
                  ("54", side), ("38", 0 if problem == "zero_qty" else qty), ("40", 2)]
        if problem != "no_price":
            fields.append(("44", f"{price:.2f}"))
        fields += [("59", 0), ("60", f"{DATE}-{clock}")]
        log("IN", build("D", firm, VENUE, fields))
        tick(0.001, 0.002)
        reason = {"no_price": "Price required", "bad_symbol": "Unknown security",
                  "zero_qty": "Invalid quantity"}[problem]
        exec_report(firm, clordid, "NONE", fields[1][1], side, fields[3][1],
                    0 if problem == "no_price" else price, 8, 8,
                    leaves=0, extra=[("58", reason)])
        continue

    # a normal new order, acknowledged by the venue
    log("IN", build("D", firm, VENUE, [("11", clordid), ("55", symbol), ("54", side),
                                       ("38", qty), ("40", 2), ("44", f"{price:.2f}"),
                                       ("59", 0), ("60", f"{DATE}-{clock}")]))
    tick(0.001, 0.002)
    order_id = str(next_order_id)
    next_order_id += 1
    exec_report(firm, clordid, order_id, symbol, side, qty, price, 0, 0)

    outcome = random.choices(["fill", "partial_cancel", "rest", "cxl_reject"],
                             weights=[45, 25, 20, 10])[0]

    if outcome == "fill":
        cum = 0
        parts = random.choice([1, 2, 2, 3])
        for p in range(parts):
            tick(1, 90)
            # split into round lots of 100; the last fill takes what is left
            fill = (qty // parts) // 100 * 100 if p < parts - 1 else qty - cum
            cum += fill
            done = cum == qty
            leaves = qty - cum
            # planted issue: one report where the venue's leaves figure is wrong
            if not planted["qty_mismatch"] and not done and firm == "FIRM4":
                leaves += 1000
                planted["qty_mismatch"] = True
            # planted issue: one corrupted message
            bad = not planted["checksum"] and i > 30 and done
            if bad:
                planted["checksum"] = True
            exec_report(firm, clordid, order_id, symbol, side, qty, price,
                        2 if done else 1, 2 if done else 1, fill, price, cum,
                        leaves, bad_checksum=bad)

    elif outcome == "partial_cancel":
        tick(1, 90)
        fill = qty // 2
        exec_report(firm, clordid, order_id, symbol, side, qty, price, 1, 1,
                    fill, price, fill)
        tick(30, 300)
        cxl = f"{firm}-C{order_count[firm]:04d}"
        log("IN", build("F", firm, VENUE, [("11", cxl), ("41", clordid), ("55", symbol),
                                           ("54", side), ("60", f"{DATE}-{clock}")]))
        tick(0.001, 0.002)
        exec_report(firm, cxl, order_id, symbol, side, qty, price, 4, 4,
                    cum=fill, leaves=0, extra=[("41", clordid)])

    elif outcome == "cxl_reject" and not planted["cxl_reject"]:
        # the order fills, then the firm tries to cancel it: too late
        tick(1, 30)
        exec_report(firm, clordid, order_id, symbol, side, qty, price, 2, 2,
                    qty, price, qty)
        tick(1, 5)
        cxl = f"{firm}-C{order_count[firm]:04d}"
        log("IN", build("F", firm, VENUE, [("11", cxl), ("41", clordid), ("55", symbol),
                                           ("54", side), ("60", f"{DATE}-{clock}")]))
        tick(0.001, 0.002)
        log("OUT", build("9", VENUE, firm, [("11", cxl), ("41", clordid), ("37", order_id),
                                            ("39", 2), ("102", 0), ("434", 1),
                                            ("58", "Too late to cancel")]))
        planted["cxl_reject"] = True

    # "rest" orders just stay on the book

    # planted issue: the venue skips three sequence numbers to FIRM3
    if not planted["gap"] and firm == "FIRM3" and i > 20:
        seq[(VENUE, "FIRM3")] += 3
        planted["gap"] = True

    # a heartbeat now and then, like a real quiet session
    if random.random() < 0.3:
        hb_firm = random.choice(FIRMS)
        tick(1, 10)
        log("IN", build("0", hb_firm, VENUE, []))
        tick(0.001, 0.002)
        log("OUT", build("0", VENUE, hb_firm, []))

tick(60, 120)
for firm in FIRMS:  # everyone logs out at the end of the day
    log("IN", build("5", firm, VENUE, []))
    tick(0.001, 0.002)
    log("OUT", build("5", VENUE, firm, []))
    tick(1, 3)

missing = [name for name, done in planted.items() if not done]
if missing:
    raise SystemExit(f"Planted issues not created, change the seed: {missing}")

os.makedirs("data", exist_ok=True)
with open("data/sample_fix.log", "w") as out:
    out.write("\n".join(lines) + "\n")
print(f"Wrote {len(lines)} lines to data/sample_fix.log")
