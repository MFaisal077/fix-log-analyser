"""
Read a FIX log and turn each line into a Python dictionary.

A log line looks like this:
    08:03:14.550 IN  8=FIX.4.2|9=132|35=D|34=2|49=FIRM1|...|10=197|

  - the time the line was logged
  - IN  = a message the venue received from a firm
    OUT = a message the venue sent to a firm
  - the FIX message itself: tag=value pairs separated by "|"
    (in a real FIX connection the separator is an invisible SOH character)
"""

# The tags this project uses, so reports can show names instead of numbers
TAG_NAMES = {
    "6": "AvgPx", "8": "BeginString", "9": "BodyLength", "10": "CheckSum",
    "11": "ClOrdID", "14": "CumQty", "17": "ExecID", "30": "LastMkt",
    "31": "LastPx", "32": "LastQty", "34": "MsgSeqNum", "35": "MsgType",
    "37": "OrderID", "38": "OrderQty", "39": "OrdStatus", "41": "OrigClOrdID",
    "44": "Price", "49": "SenderCompID", "52": "SendingTime", "54": "Side",
    "55": "Symbol", "56": "TargetCompID", "58": "Text", "102": "CxlRejReason",
    "108": "HeartBtInt", "150": "ExecType", "151": "LeavesQty",
    "434": "CxlRejResponseTo",
}

MSG_TYPES = {
    "0": "Heartbeat", "5": "Logout", "8": "ExecutionReport", "9": "OrderCancelReject",
    "A": "Logon", "D": "NewOrderSingle", "F": "OrderCancelRequest",
    "G": "OrderCancelReplaceRequest",
}

EXEC_TYPES = {
    "0": "New", "1": "Partial fill", "2": "Fill", "4": "Cancelled",
    "5": "Replaced", "8": "Rejected",
}


def parse_line(line):
    """Split one log line into a dictionary of tag -> value.

    The log's own time and direction are stored under "time" and "dir",
    and the raw FIX text under "raw" (needed later to check the checksum).
    Returns None for blank or broken lines.
    """
    parts = line.strip().split(maxsplit=2)   # time, direction, message
    if len(parts) < 3:
        return None

    time, direction, raw = parts
    msg = {"time": time, "dir": direction, "raw": raw}
    for pair in raw.split("|"):
        if "=" in pair:
            tag, value = pair.split("=", 1)   # split on the first "=" only
            msg[tag] = value
    return msg


def load_messages(path):
    """Read a whole log file and return a list of parsed messages."""
    messages = []
    with open(path) as f:
        for line in f:
            msg = parse_line(line)
            if msg is not None:
                messages.append(msg)
    return messages


def firm_of(msg):
    """The firm on the other side: the sender for IN, the target for OUT."""
    return msg.get("49") if msg["dir"] == "IN" else msg.get("56")
