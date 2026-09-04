# Settlement Q&A Agent — Track 04, RazorPay Buildathon

An agent that closes one finance-ops loop: it reconciles a payment gateway's
transaction ledger against a bank settlement file, reports a match rate and
an honest exception list, and lets you interrogate the result in plain
English ("why wasn't pay_100002 settled cleanly?").

**Two-part design, on purpose:**
- `reconcile.py` — deterministic Python matching engine. No LLM. This is
  what actually decides what matched and what didn't, so the numbers you
  show judges are always exact.
- `qa_agent.py` — Claude, wired up with **tool use**, that reads the
  reconciliation output through tools and answers questions about it. It
  never invents a number; it always calls a tool first.

This matters for "the bar" on your track: throughput + measured accuracy +
an honest exception list, not a cherry-picked demo match.

---

## 0. What you need before you start

- A laptop with internet access.
- **Python 3.10+**. Check by opening a terminal and typing `python3 --version`.
  If you don't have Python: go to https://www.python.org/downloads/, click
  the yellow "Download Python" button, run the installer, and on the first
  install screen **tick "Add python.exe to PATH"** before clicking Install.
- An **Anthropic API key**. Go to https://console.anthropic.com, sign in
  (or sign up), click **Settings** in the left sidebar → **API Keys** →
  **Create Key**, give it any name, and copy the key that starts with
  `sk-ant-`. You'll paste this in step 3. (New accounts get free trial
  credit, which is plenty for a night of demoing.)

---

## 1. Get the project onto your machine

Unzip the project folder you downloaded (`settlement-qa-agent.zip`) onto
your Desktop, or wherever you want to work. Open a terminal and move into
it:

```bash
cd path/to/settlement-qa-agent
```

You should see three folders: `data/`, `backend/`, `frontend/`, and this
`README.md`.

---

## 2. Install the Python dependencies

Still in the project root:

```bash
cd backend
pip install -r requirements.txt --break-system-packages
```

(Drop `--break-system-packages` if you're on Windows or inside a virtual
environment — it's only needed on some Linux/Mac setups that lock down
system Python. If you want a clean virtual environment instead:
`python3 -m venv venv && source venv/bin/activate` — or on Windows,
`venv\Scripts\activate` — then run the `pip install` line without the
extra flag.)

---

## 3. Add your API key

Still inside `backend/`:

```bash
cp .env.example .env
```

Open the new `.env` file in any text editor (VS Code: right-click it in
the file explorer → "Open") and replace the placeholder with your real
key, so the line reads:

```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Save the file.

---

## 4. Generate the synthetic data

This is your "50+ record batch of synthetic data." Run it from inside
`data/`:

```bash
cd ../data
python3 generate_data.py
```

You should see:
```
Wrote 62 transactions -> transactions.csv
Wrote 63 settlement rows -> bank_settlements.csv
```

Open `transactions.csv` in Excel/Sheets/VS Code if you want to eyeball it —
it's a realistic gateway-style ledger (payment_id, amount, fee, tax,
net_expected). `bank_settlements.csv` is the bank's side, with real
exceptions baked in on purpose: some payments never got settled, some
settled for the wrong amount, some settled twice, some settled late.

Re-run this script any time before your demo to get a fresh, differently-
seeded batch.

---

## 5. Start the backend API

From inside `backend/`:

```bash
cd ../backend
uvicorn app:app --reload --port 8000
```

Leave this terminal window running — it's your server. You should see:
```
Uvicorn running on http://127.0.0.1:8000
```

To sanity-check it's alive, open http://localhost:8000/api/health in a
browser — it should show `{"ok":true}`.

---

## 6. Open the frontend

Open a **second** terminal window (don't close the one running uvicorn),
then just open the HTML file directly:

```bash
cd path/to/settlement-qa-agent/frontend
open index.html        # Mac
xdg-open index.html    # Linux
start index.html       # Windows
```

Or simplest of all: find `index.html` in your file explorer and
double-click it — it opens in your default browser.

---

## 7. Run the demo

1. Click **"Reconcile a fresh batch"**. The left panel fills in with a
   match rate, transaction count, and rupee amount at risk, plus the full
   exception list (color-coded by reason: missing, amount mismatch,
   delayed, duplicate, unknown).
2. On the right, click one of the suggested chips, or type your own
   question, e.g.:
   - "What's the overall match rate?"
   - "List every missing settlement over ₹1000"
   - "Why wasn't pay_100014 settled cleanly?"
   - "How much money is at risk from duplicate settlements?"
3. Watch the agent answer — every number it gives came from a tool call
   into the deterministic report, not from guessing.

For the judges, this is worth saying out loud: **the reconciliation math
is deterministic Python; the LLM is only the question-answering layer on
top of it, grounded via tool use.** That's the honest-exception-list bar
the brief asks for.

---

## 8. If something breaks

- **"Couldn't reach the backend"** in the browser → make sure the uvicorn
  terminal from step 5 is still running and says `Uvicorn running on
  http://127.0.0.1:8000`.
- **`ANTHROPIC_API_KEY is not set`** → you skipped step 3, or didn't save
  the `.env` file, or restarted the terminal after creating it without
  `cd`-ing back into `backend/`. Re-check `backend/.env` has your real key
  on one line with no quotes.
- **`ModuleNotFoundError`** → you're not in the right Python environment,
  or step 2's `pip install` didn't finish. Re-run
  `pip install -r requirements.txt --break-system-packages` from inside
  `backend/`.
- **Port 8000 already in use** → run
  `uvicorn app:app --reload --port 8001` instead, and change the `API`
  constant near the top of `frontend/index.html`'s `<script>` block to
  `http://localhost:8001`.

---

## 9. Ideas if you have extra time before submission

- Swap the synthetic CSVs for a real (or more realistic) Razorpay
  settlement/payout export format.
- Add a `/api/ask` streaming response so answers appear token-by-token.
- Add a second agent tool, `explain_fee_variance`, that breaks down why a
  merchant's effective fee % differs from their contracted rate.
- Log every question + answer to a file and show it in the README as your
  "measured accuracy" evidence — i.e., a small eval set of Q/A pairs you
  wrote by hand, with pass/fail, so you can *prove* the match rate claim
  rather than just assert it live.

Good luck tonight.
