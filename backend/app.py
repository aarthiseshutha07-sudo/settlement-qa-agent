"""
app.py
------
Thin FastAPI layer over reconcile.py (deterministic engine) and
qa_agent.py (Claude-powered Q&A). This is what the frontend talks to.

Run with:
    uvicorn app:app --reload --port 8000
"""

import os
import subprocess
import sys

from dotenv import load_dotenv
load_dotenv()  # picks up backend/.env if present, so ANTHROPIC_API_KEY doesn't need a shell export

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import reconcile

app = FastAPI(title="Settlement Q&A Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for a hackathon demo; scope this down for real use
    allow_methods=["*"],
    allow_headers=["*"],
)

_agent = None  # lazy-loaded so the server can boot even before ANTHROPIC_API_KEY is set


def get_agent():
    global _agent
    if _agent is None:
        from qa_agent import SettlementQAAgent
        _agent = SettlementQAAgent()
    return _agent


class AskRequest(BaseModel):
    question: str


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/generate")
def generate_data():
    """Regenerate a fresh synthetic batch (simulates a new day's data landing)."""
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    result = subprocess.run([sys.executable, "generate_data.py"], cwd=data_dir,
                             capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(500, result.stderr)
    return {"ok": True, "log": result.stdout}


@app.post("/api/reconcile")
def run_reconcile():
    """Run the deterministic matching engine and return the summary + exceptions."""
    report = reconcile.run()
    if _agent is not None:
        _agent.reload()
    return report


@app.get("/api/report")
def get_report():
    import json
    if not os.path.exists(reconcile.REPORT_PATH):
        raise HTTPException(404, "No report yet -- call /api/reconcile first.")
    with open(reconcile.REPORT_PATH) as f:
        return json.load(f)


@app.post("/api/ask")
def ask(req: AskRequest):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(400, "ANTHROPIC_API_KEY is not set on the server. See .env.example.")
    if not os.path.exists(reconcile.REPORT_PATH):
        raise HTTPException(400, "No reconciliation report yet -- call /api/reconcile first.")
    try:
        answer = get_agent().ask(req.question)
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"question": req.question, "answer": answer}
