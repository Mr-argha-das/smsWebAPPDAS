# FinanceFlow Phase 1

FastAPI + MongoDB finance management web app with JWT cookie auth, Mongoengine class-based models, workspaces, transactions, auto-generated journal entries, and per-account ledgers.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

MongoDB should be running locally, or set `MONGODB_URI` in `.env`.

## Accounting Posting Rule

Each transaction posts two lines:

- Debit: selected `Debit Account`
- Credit: selected `Credit Account`

This creates one `JournalEntry` and two `LedgerEntry` records. Ledger balances follow normal accounting balance rules: assets and expenses increase by debit, while liabilities, equity, and revenue increase by credit.
