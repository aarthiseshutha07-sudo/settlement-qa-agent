"""
qa_agent.py
-----------
The "Settlement Q&A Agent" itself.

Design choice (important for judges): the LLM never invents reconciliation
numbers. It is given tools that read straight from reconciliation_report.json
(produced deterministically by reconcile.py) and it must call those tools to
answer anything about specific payments/amounts. This keeps every number in
every answer traceable back to the report -- no hallucinated match rates.

Requires: ANTHROPIC_API_KEY in the environment (see .env.example).
"""

import json
import os

from anthropic import Anthropic

MODEL = "claude-sonnet-4-5"  # swap for any current Claude model you have access to

REPORT_PATH = os.path.join(os.path.dirname(__file__), "reconciliation_report.json")

SYSTEM_PROMPT = """You are the Settlement Q&A Agent for a merchant finance team.
You answer questions about a batch reconciliation between the payment gateway's
transaction ledger and the bank's settlement file.

Rules:
1. Never guess a number. Always call a tool to look up match rates, specific
   payments, or exception lists before answering anything quantitative.
2. When you explain an exception, name its reason code in plain language
   (e.g. "it was never settled by the bank" rather than "MISSING_SETTLEMENT")
   and give the rupee amount involved.
3. Keep answers short and finance-ops appropriate: a couple of sentences or a
   tight bullet list. No filler, no apologies.
4. If a payment_id isn't found anywhere in the data, say so plainly -- don't
   speculate about why.
"""

TOOLS = [
    {
        "name": "get_summary",
        "description": "Get the overall reconciliation summary: match rate, totals, and exception counts by reason.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_payment",
        "description": "Look up everything known about one payment_id: whether it matched, and if not, why.",
        "input_schema": {
            "type": "object",
            "properties": {"payment_id": {"type": "string", "description": "e.g. pay_100014"}},
            "required": ["payment_id"],
        },
    },
    {
        "name": "list_exceptions",
        "description": "List exceptions, optionally filtered by reason code and/or a minimum absolute amount at risk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "enum": ["MISSING_SETTLEMENT", "AMOUNT_MISMATCH", "DELAYED_SETTLEMENT",
                             "DUPLICATE_SETTLEMENT", "UNKNOWN_SETTLEMENT"],
                    "description": "Optional. Omit to return all reasons.",
                },
                "min_amount": {"type": "number", "description": "Optional. Only include exceptions with |amount_delta| >= this."},
                "limit": {"type": "integer", "description": "Max rows to return. Default 20."},
            },
        },
    },
]


class SettlementQAAgent:
    def __init__(self, report_path: str = REPORT_PATH, api_key: str | None = None):
        self.report_path = report_path
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self._report = None

    # ---- data access (deterministic, no LLM involved) -------------------
    @property
    def report(self):
        if self._report is None:
            with open(self.report_path) as f:
                self._report = json.load(f)
        return self._report

    def reload(self):
        self._report = None
        return self.report

    def _tool_get_summary(self):
        return self.report["summary"]

    def _tool_get_payment(self, payment_id: str):
        for m in self.report["matched"]:
            if m["payment_id"] == payment_id:
                return {"status": "MATCHED", **m}
        for e in self.report["exceptions"]:
            if e["payment_id"] == payment_id:
                return {"status": "EXCEPTION", **e}
        return {"status": "NOT_FOUND", "payment_id": payment_id}

    def _tool_list_exceptions(self, reason: str = None, min_amount: float = None, limit: int = 20):
        rows = self.report["exceptions"]
        if reason:
            rows = [r for r in rows if r["reason"] == reason]
        if min_amount is not None:
            rows = [r for r in rows if abs(r["amount_delta"]) >= min_amount]
        rows = sorted(rows, key=lambda r: abs(r["amount_delta"]), reverse=True)
        return rows[:limit]

    def _dispatch(self, name: str, tool_input: dict):
        if name == "get_summary":
            return self._tool_get_summary()
        if name == "get_payment":
            return self._tool_get_payment(**tool_input)
        if name == "list_exceptions":
            return self._tool_list_exceptions(**tool_input)
        return {"error": f"unknown tool {name}"}

    # ---- the actual agent loop -------------------------------------------
    def ask(self, question: str, max_turns: int = 4) -> str:
        messages = [{"role": "user", "content": question}]

        for _ in range(max_turns):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=700,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            if response.stop_reason != "tool_use":
                return "".join(b.text for b in response.content if b.type == "text").strip()

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self._dispatch(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })
            messages.append({"role": "user", "content": tool_results})

        return "I wasn't able to resolve that within the tool-call budget -- try a more specific question."


if __name__ == "__main__":
    # quick manual smoke test: `python3 qa_agent.py "your question"`
    import sys
    agent = SettlementQAAgent()
    q = " ".join(sys.argv[1:]) or "What's the overall match rate and what's the biggest exception?"
    print("Q:", q)
    print("A:", agent.ask(q))
