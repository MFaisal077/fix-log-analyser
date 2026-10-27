"""
Load the execution reports from a FIX log into a SQLite database, so the
day can be checked with SQL (see queries.sql).

Usage:
    python load_to_sqlite.py data/sample_fix.log      creates fix.db
    sqlite3 fix.db < queries.sql                       runs every query
"""

import sqlite3
import sys

from fixlog import firm_of, load_messages

COLUMNS = """
    time       TEXT,
    firm       TEXT,
    clordid    TEXT,    -- 11: the firm's ID for the order
    orig_clordid TEXT,  -- 41: the order a cancel points back to
    order_id   TEXT,    -- 37: the venue's ID for the order
    symbol     TEXT,    -- 55
    side       TEXT,    -- 54: 1 = buy, 2 = sell
    exec_type  TEXT,    -- 150: 0 new, 1 partial, 2 fill, 4 cancelled, 8 rejected
    ord_status TEXT,    -- 39
    order_qty  INTEGER, -- 38
    last_qty   INTEGER, -- 32: shares in this fill
    last_px    REAL,    -- 31: price of this fill
    cum_qty    INTEGER, -- 14: shares filled so far
    leaves_qty INTEGER, -- 151: shares still open
    text       TEXT     -- 58: reject reason
"""


def main(log_path, db_path="fix.db"):
    messages = load_messages(log_path)
    reports = [m for m in messages if m.get("35") == "8"]

    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS executions")
    con.execute(f"CREATE TABLE executions ({COLUMNS})")

    rows = [(m["time"], firm_of(m), m.get("11"), m.get("41"), m.get("37"),
             m.get("55"), m.get("54"), m.get("150"), m.get("39"),
             int(m["38"]), int(m["32"]), float(m["31"]), int(m["14"]),
             int(m["151"]), m.get("58"))
            for m in reports]
    con.executemany("INSERT INTO executions VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    con.commit()
    con.close()
    print(f"Loaded {len(rows)} execution reports into {db_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python load_to_sqlite.py <logfile>")
    main(sys.argv[1])
