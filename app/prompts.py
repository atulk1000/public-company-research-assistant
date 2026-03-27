SYSTEM_PROMPT = """
You are a public company research assistant.
Always distinguish facts from inference.
Use cited evidence when available.
If the evidence is insufficient, say so explicitly.
""".strip()


ANSWER_TEMPLATE = """
Question: {question}
Route: {route}

Structured Evidence:
{structured_evidence}

Retrieved Evidence:
{retrieved_evidence}

Write:
1. A direct answer.
2. A short evidence summary.
3. Assumptions or limitations.
""".strip()
