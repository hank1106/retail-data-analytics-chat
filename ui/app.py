"""Chat UI for the Retail Data Analytics system (Streamlit).

Run with::

    streamlit run ui/app.py

By default the UI talks to the query engine in-process (no server needed).
Set ``BACKEND_URL=http://localhost:8000`` to route through the FastAPI
server instead (see README).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from retail_chat.config import PROJECT_ROOT, Settings  # noqa: E402
from retail_chat.data_loader import ensure_database  # noqa: E402
from retail_chat.db import connect  # noqa: E402
from retail_chat.llm import build_responder  # noqa: E402
from retail_chat.repository import RetailRepository  # noqa: E402
from retail_chat.service import EXAMPLE_QUERIES, process_query  # noqa: E402

BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")


def _inprocess_answer(message: str) -> tuple[str, str, dict]:
    settings = Settings.from_env()
    db = ensure_database()
    conn = connect(db)
    try:
        repo = RetailRepository(conn)
        responder = build_responder(settings)
        result = process_query(message, repo, responder)
        return result.answer, result.intent, result.entities
    finally:
        conn.close()


def _remote_answer(message: str) -> tuple[str, str, dict]:
    import json
    import urllib.request

    req = urllib.request.Request(
        f"{BACKEND_URL}/api/chat",
        data=json.dumps({"message": message}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["answer"], body.get("intent", ""), body.get("entities", {})


def answer(message: str) -> tuple[str, str, dict]:
    if BACKEND_URL:
        try:
            return _remote_answer(message)
        except Exception as exc:  # server down -> transparent fallback
            st.warning(f"API server unreachable ({exc}); using in-process engine.")
    return _inprocess_answer(message)


st.set_page_config(page_title="Retail Analytics Chat", page_icon="🛒")
st.title("🛒 Retail Analytics Chat")
st.caption(
    "Ask about customers, products or business metrics. "
    f"Engine: {'API server' if BACKEND_URL else 'in-process'}."
)

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hi! Ask me about a customer (e.g. C10001), "
            "a product (e.g. P1001) or overall sales.",
            "intent": "help",
            "entities": {},
        }
    ]

with st.sidebar:
    st.header("Try these")
    for q in EXAMPLE_QUERIES:
        if st.button(q, key=q):
            st.session_state.messages.append({"role": "user", "content": q})
            st.rerun()
    if st.button("Clear chat"):
        st.session_state.messages = st.session_state.messages[:1]
        st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("intent"):
            with st.expander("How I understood this"):
                st.write(f"Intent: `{msg['intent']}`")
                st.write(f"Entities: `{msg.get('entities', {})}`")

prompt = st.chat_input("Ask about customers, products or sales…")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Looking that up…"):
            text, intent, entities = answer(prompt)
        st.markdown(text)
        with st.expander("How I understood this"):
            st.write(f"Intent: `{intent}`")
            st.write(f"Entities: `{entities}`")
    st.session_state.messages.append(
        {"role": "assistant", "content": text, "intent": intent, "entities": entities}
    )
