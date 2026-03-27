from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.hybrid_tool import answer_question

st.set_page_config(page_title="Public Company Research Assistant", layout="wide")

st.title("Public Company Research Assistant")
st.caption("Hybrid SQL + RAG starter for public company narrative-vs-numbers analysis.")

default_question = "Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters."
question = st.text_area("Ask a question", value=default_question, height=120)

if st.button("Run Analysis", type="primary"):
    result = answer_question(question)
    st.subheader("Route")
    st.code(result["route"])

    st.subheader("Answer")
    st.write(result["answer"])

    st.subheader("Structured Evidence")
    st.json(result["structured_evidence"])

    st.subheader("Retrieved Evidence")
    st.json(result["retrieved_evidence"])
