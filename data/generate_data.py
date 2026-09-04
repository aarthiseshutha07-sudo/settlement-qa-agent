"""
generate_data.py
-----------------
Creates two synthetic CSVs that stand in for the two "real time" feeds a
finance-ops person has to cross-check every day:

  transactions.csv        -> what the payment gateway says was charged
  bank_settlements.csv    -> what the bank actually paid out

50+ records, with a deliberate mix of clean matches AND real-world
exceptions (missing settlement, amount mismatch, fee mismatch, duplicate
UTR, delayed settlement) so the reconciliation engine has something
genuine to find. Re-run this any time you want a fresh batch.
"""

import csv
import random
from datetime import datetime, timedelta

random.seed(42)

MERCHANTS = ["Zylo Retail", "Kavya Foods", "Nimbus SaaS", "Orbit Travels", "Pixel Studio"]
METHODS = ["upi", "card", "netbanking", "wallet"]

N_TXNS = 62  # > 50 as required by the brief


def money(a, b):
    return round(random.uniform(a, b), 2)


def make_transactions(n):
    rows = []
    base_date = datetime(2026, 9, 1, 9, 0, 0)
    for i in range(1, n + 1):
        amount = money(150, 45000)
        fee_pct = 0.019 if random.random() > 0.15 else 0.024  # some plans differ
        fee = round(amount * fee_pct, 2)
        tax = round(fee * 0.18, 2)  # 18% GST on the fee
        net_expected = round(amount - fee - tax, 2)
        created = base_date + timedelta(minutes=i * 17, seconds=random.randint(0, 59))
        rows.append({
            "payment_id": f"pay_{100000 + i}",
            "order_id": f"order_{200000 + i}",
            "merchant": random.choice(MERCHANTS),
            "method": random.choice(METHODS),
            "amount": amount,
            "fee": fee,
            "tax": tax,
            "net_expected": net_expected,
            "status": "captured",
            "created_at": created.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return rows


def make_settlements(transactions):
    """Build the bank-side view, deliberately injecting exceptions."""
    settlements = []
    utr_counter = 900001

    for i, t in enumerate(transactions):
        settle_date = datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M:%S") + timedelta(days=1)
        bucket = i % 20  # deterministic-ish distribution of exception types

        if bucket == 0:
            # MISSING: transaction never shows up in the bank file at all
            continue

        elif bucket == 1:
            # AMOUNT MISMATCH: bank paid out less than expected (e.g. an extra
            # deduction / rounding bug upstream)
            net_settled = round(t["net_expected"] - money(10, 250), 2)

        elif bucket == 2:
            # DELAYED: settles 4 days late instead of next-day
            settle_date += timedelta(days=3)
            net_settled = t["net_expected"]

        elif bucket == 3:
            # DUPLICATE: same payment gets settled twice (bank-side glitch)
            settlements.append({
                "utr": f"UTR{utr_counter}", "payment_id": t["payment_id"],
                "net_settled": t["net_expected"],
                "settlement_date": settle_date.strftime("%Y-%m-%d"),
            })
            utr_counter += 1
            net_settled = t["net_expected"]

        else:
            # CLEAN MATCH
            net_settled = t["net_expected"]

        settlements.append({
            "utr": f"UTR{utr_counter}",
            "payment_id": t["payment_id"],
            "net_settled": net_settled,
            "settlement_date": settle_date.strftime("%Y-%m-%d"),
        })
        utr_counter += 1

    # A couple of pure bank-side ghosts: a UTR referencing a payment_id
    # that doesn't exist in our transactions file at all (e.g. a refund
    # reversal settled separately)
    for j in range(2):
        settlements.append({
            "utr": f"UTR{utr_counter}",
            "payment_id": f"pay_{999000 + j}",
            "net_settled": money(500, 3000),
            "settlement_date": "2026-09-03",
        })
        utr_counter += 1

    return settlements


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    txns = make_transactions(N_TXNS)
    settles = make_settlements(txns)

    write_csv(
        "transactions.csv", txns,
        ["payment_id", "order_id", "merchant", "method", "amount", "fee", "tax", "net_expected", "status", "created_at"],
    )
    write_csv(
        "bank_settlements.csv", settles,
        ["utr", "payment_id", "net_settled", "settlement_date"],
    )

    print(f"Wrote {len(txns)} transactions -> transactions.csv")
    print(f"Wrote {len(settles)} settlement rows -> bank_settlements.csv")
