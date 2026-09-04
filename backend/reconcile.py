"""
reconcile.py
------------
The non-AI "ground truth" half of the agent: deterministic matching logic
between the gateway's transactions.csv and the bank's bank_settlements.csv.

This is intentionally NOT sent through an LLM -- reconciliation math must
be exact, not probabilistic. The LLM (qa_agent.py) only ever *talks about*
the output of this file; it never invents match/mismatch decisions itself.

Produces a single reconciliation_report.json with:
  - summary: match rate + totals
  - matched: list of clean matches
  - exceptions: list of {payment_id, reason, detail, amount_delta}
"""

import json
import os
from collections import defaultdict

import pandas as pd

AMOUNT_TOLERANCE = 1.00  # rupees; anything beyond this is a real mismatch
DELAY_TOLERANCE_DAYS = 1  # T+1 is normal; more than that is "delayed"

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TXN_PATH = os.path.join(DATA_DIR, "transactions.csv")
SETTLE_PATH = os.path.join(DATA_DIR, "bank_settlements.csv")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "reconciliation_report.json")


def load_data():
    txns = pd.read_csv(TXN_PATH)
    settles = pd.read_csv(SETTLE_PATH)
    return txns, settles


def reconcile(txns: pd.DataFrame, settles: pd.DataFrame):
    settles_by_payment = defaultdict(list)
    for _, row in settles.iterrows():
        settles_by_payment[row["payment_id"]].append(row)

    matched = []
    exceptions = []
    seen_payment_ids = set(txns["payment_id"])

    for _, t in txns.iterrows():
        pid = t["payment_id"]
        rows = settles_by_payment.get(pid, [])

        if not rows:
            exceptions.append({
                "payment_id": pid,
                "reason": "MISSING_SETTLEMENT",
                "detail": f"No bank settlement found for {pid}, expected net {t['net_expected']}.",
                "amount_delta": round(float(t["net_expected"]), 2),
                "expected_net": round(float(t["net_expected"]), 2),
                "settled_net": None,
                "created_at": t["created_at"],
            })
            continue

        if len(rows) > 1:
            exceptions.append({
                "payment_id": pid,
                "reason": "DUPLICATE_SETTLEMENT",
                "detail": f"{pid} was settled {len(rows)} times (UTRs: {', '.join(r['utr'] for r in rows)}).",
                "amount_delta": round(float(rows[0]["net_settled"]) * (len(rows) - 1), 2),
                "expected_net": round(float(t["net_expected"]), 2),
                "settled_net": round(float(sum(r["net_settled"] for r in rows)), 2),
                "created_at": t["created_at"],
            })
            continue

        settle = rows[0]
        delta = round(float(settle["net_settled"]) - float(t["net_expected"]), 2)
        days_to_settle = (
            pd.to_datetime(settle["settlement_date"]) - pd.to_datetime(t["created_at"]).normalize()
        ).days

        if abs(delta) > AMOUNT_TOLERANCE:
            exceptions.append({
                "payment_id": pid,
                "reason": "AMOUNT_MISMATCH",
                "detail": f"{pid} expected net {t['net_expected']} but bank settled {settle['net_settled']} "
                          f"(delta {delta:+.2f}).",
                "amount_delta": delta,
                "expected_net": round(float(t["net_expected"]), 2),
                "settled_net": round(float(settle["net_settled"]), 2),
                "created_at": t["created_at"],
            })
        elif days_to_settle > DELAY_TOLERANCE_DAYS:
            exceptions.append({
                "payment_id": pid,
                "reason": "DELAYED_SETTLEMENT",
                "detail": f"{pid} settled {days_to_settle} day(s) after capture (expected T+1).",
                "amount_delta": 0.0,
                "expected_net": round(float(t["net_expected"]), 2),
                "settled_net": round(float(settle["net_settled"]), 2),
                "created_at": t["created_at"],
                "settlement_date": settle["settlement_date"],
            })
        else:
            matched.append({
                "payment_id": pid,
                "utr": settle["utr"],
                "net_settled": round(float(settle["net_settled"]), 2),
                "settlement_date": settle["settlement_date"],
            })

    # Bank-side ghosts: settlement rows whose payment_id never appears in
    # our transactions feed at all.
    for pid, rows in settles_by_payment.items():
        if pid not in seen_payment_ids:
            for r in rows:
                exceptions.append({
                    "payment_id": pid,
                    "reason": "UNKNOWN_SETTLEMENT",
                    "detail": f"Bank settled {r['utr']} for {pid}, which has no matching transaction record.",
                    "amount_delta": round(float(r["net_settled"]), 2),
                    "expected_net": None,
                    "settled_net": round(float(r["net_settled"]), 2),
                    "created_at": None,
                })

    total = len(txns)
    match_rate = round(100 * len(matched) / total, 2) if total else 0.0

    reason_counts = defaultdict(int)
    for e in exceptions:
        reason_counts[e["reason"]] += 1

    report = {
        "summary": {
            "total_transactions": total,
            "matched_count": len(matched),
            "exception_count": len(exceptions),
            "match_rate_pct": match_rate,
            "reason_breakdown": dict(reason_counts),
            "total_amount_at_risk": round(sum(abs(e["amount_delta"]) for e in exceptions), 2),
        },
        "matched": matched,
        "exceptions": exceptions,
    }
    return report


def run():
    txns, settles = load_data()
    report = reconcile(txns, settles)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report["summary"], indent=2))
    return report


if __name__ == "__main__":
    run()
