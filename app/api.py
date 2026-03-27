from fastapi import FastAPI
from pydantic import BaseModel

from agent.hybrid_tool import answer_question

app = FastAPI(title="Public Company Research Assistant", version="0.1.0")


class QuestionRequest(BaseModel):
    question: str


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
def ask_question(request: QuestionRequest) -> dict:
    return answer_question(request.question)
