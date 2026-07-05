"""Veles Finance Agent — Streamlit chat UI."""

import html
import json
import os
import re
import time

import requests
import streamlit as st

API_BASE = os.getenv("VELES_API_URL", "http://localhost:8000/api/v1")
DEMO_EMAIL = "demo@veles.finance"
DEMO_PASSWORD = "VelesDemo2026!"

st.set_page_config(
    page_title="Veles Finance Agent",
    page_icon="🏛",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.report-block {
    background: #0e1117;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    padding: 20px 24px;
    font-family: 'Courier New', monospace;
    font-size: 13.5px;
    color: #e8e8e8;
    white-space: pre-wrap;
    line-height: 1.65;
    word-break: break-word;
}
.thinking-block {
    background: #0a0a12;
    border-left: 3px solid #3a3a5a;
    border-radius: 4px;
    padding: 10px 14px;
    font-family: 'Courier New', monospace;
    font-size: 12px;
    color: #6868a0;
    white-space: pre-wrap;
    max-height: 260px;
    overflow-y: auto;
}
.verdict-approved {
    background: linear-gradient(135deg, #0d4f2b, #1a7a42);
    border: 1px solid #2ecc71;
    border-radius: 8px;
    padding: 14px 20px;
    font-family: 'Courier New', monospace;
    font-size: 18px;
    font-weight: bold;
    color: #2ecc71;
    text-align: center;
    letter-spacing: 3px;
    margin-top: 12px;
}
.verdict-rejected {
    background: linear-gradient(135deg, #4f0d0d, #7a1a1a);
    border: 1px solid #e74c3c;
    border-radius: 8px;
    padding: 14px 20px;
    font-family: 'Courier New', monospace;
    font-size: 18px;
    font-weight: bold;
    color: #e74c3c;
    text-align: center;
    letter-spacing: 3px;
    margin-top: 12px;
}
</style>
""", unsafe_allow_html=True)


# ── Text processing ────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Remove all markdown symbols, then HTML-escape for safe <div> insertion."""
    # bold / italic: **x**, *x*, __x__, _x_
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"\*\*(.+?)\*\*",     r"\1", text, flags=re.DOTALL)
    text = re.sub(r"\*(.+?)\*",         r"\1", text, flags=re.DOTALL)
    text = re.sub(r"___(.+?)___",       r"\1", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__",         r"\1", text, flags=re.DOTALL)
    text = re.sub(r"_(.+?)_",           r"\1", text, flags=re.DOTALL)
    # inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # headings ## → UPPERCASE
    text = re.sub(r"^#{1,6}\s+(.+)$", lambda m: m.group(1).upper(), text, flags=re.MULTILINE)
    # markdown bullets → •
    text = re.sub(r"^[ \t]*[-*]\s+", "  •  ", text, flags=re.MULTILINE)
    # HTML-escape so < > & don't break the surrounding div
    return html.escape(text)


def _split(text: str) -> tuple[str, str]:
    """Extract (thinking, output) from model response tags."""
    thinking, output = "", text
    m = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL)
    if m:
        thinking = m.group(1).strip()
        output = text[m.end():].strip()
    m2 = re.search(r"<output>(.*?)</output>", output, re.DOTALL)
    if m2:
        output = m2.group(1).strip()
    return thinking, output


def _verdict(text: str) -> str | None:
    u = text.upper()
    if "VERDICT" in u and "APPROVED" in u:
        return "APPROVED"
    if "VERDICT" in u and "REJECTED" in u:
        return "REJECTED"
    return None


def _render(text: str):
    """Display one assistant message: thinking (collapsible) + report + verdict."""
    thinking, output = _split(text)

    if thinking:
        st.markdown(
            f"<details><summary>Agent reasoning ({len(thinking.split())} words)"
            f"</summary><div class='thinking-block'>{html.escape(thinking)}</div></details>",
            unsafe_allow_html=True,
        )

    body = _clean(output if output else text)
    st.markdown(f'<div class="report-block">{body}</div>', unsafe_allow_html=True)

    v = _verdict(text)
    if v == "APPROVED":
        st.markdown('<div class="verdict-approved">VERDICT: APPROVED ✓</div>', unsafe_allow_html=True)
    elif v == "REJECTED":
        st.markdown('<div class="verdict-rejected">VERDICT: REJECTED ✗</div>', unsafe_allow_html=True)


# ── API helpers ────────────────────────────────────────────────────────────────

def _api_post(path: str, token: str = "", body: dict | None = None,
              form: dict | None = None) -> dict | None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        if form:
            r = requests.post(f"{API_BASE}{path}", headers=headers, data=form, timeout=10)
        else:
            r = requests.post(f"{API_BASE}{path}", headers=headers, json=body, timeout=10)
        return r.json() if r.ok else None
    except Exception:
        return None


def _api_get(path: str, token: str) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}{path}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=8)
        return r.json() if r.ok else None
    except Exception:
        return None


def _login() -> str | None:
    """Return user JWT, auto-registering on first run."""
    data = {"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "grant_type": "password"}
    resp = _api_post("/auth/login", form=data)
    if resp and "access_token" in resp:
        return resp["access_token"]
    # First run: register then retry
    _api_post("/auth/register",
              body={"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "username": "Demo"})
    resp = _api_post("/auth/login", form=data)
    return resp.get("access_token") if resp else None


def _new_session(user_token: str) -> str | None:
    resp = _api_post("/auth/session", token=user_token)
    if resp:
        return resp.get("token", {}).get("access_token")
    return None


def _ensure_session() -> str | None:
    """Return a valid session token.

    Restoration order:
      1. session_state  (normal rerun — never lost)
      2. URL param ?t=  (survives F5 page refresh)
      3. Create new     (brand new chat)
    """
    if "session_token" in st.session_state:
        return st.session_state["session_token"]

    # Restore from URL after page refresh
    url_token = st.query_params.get("t")
    if url_token:
        st.session_state["session_token"] = url_token
        return url_token

    # Create new session
    user_token = _login()
    if not user_token:
        return None
    session_token = _new_session(user_token)
    if not session_token:
        return None

    st.session_state["session_token"] = session_token
    # Save in URL so page refresh can restore it
    st.query_params["t"] = session_token
    return session_token


def _load_history(token: str) -> list[dict]:
    resp = _api_get("/chatbot/messages", token)
    if resp:
        return [{"role": m["role"], "content": m["content"]}
                for m in resp.get("messages", [])]
    return []


def _stream(token: str, message: str):
    """Yield text chunks from the streaming endpoint."""
    try:
        with requests.post(
            f"{API_BASE}/chatbot/chat/stream",
            headers={"Authorization": f"Bearer {token}"},
            json={"messages": [{"role": "user", "content": message}]},
            stream=True,
            timeout=120,
        ) as resp:
            if not resp.ok:
                yield f"[Error {resp.status_code}] {resp.text}"
                return
            for line in resp.iter_lines():
                if line and line.startswith(b"data: "):
                    try:
                        d = json.loads(line[6:])
                        chunk = d.get("content", "")
                        # Skip internal tool-call notifications (start with null byte)
                        if chunk and not chunk.startswith("\x00"):
                            yield chunk
                        if d.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
    except requests.exceptions.ConnectionError:
        yield "[Connection error] — run: make docker-up"
    except Exception as e:
        yield f"[Error] {e}"


# ── Main UI ────────────────────────────────────────────────────────────────────

def main():
    # Header
    c1, c2, c3 = st.columns([1, 7, 2])
    with c1:
        st.markdown("## 🏛")
    with c2:
        st.markdown("## Veles Finance Agent")
        st.caption("Institutional analysis · Live data · Always gives a verdict")
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("New chat", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            # Remove session token from URL
            st.query_params.clear()
            st.rerun()

    st.divider()

    # Auth — must happen before rendering anything else
    token = _ensure_session()
    if not token:
        st.error("Cannot connect to backend. Run: make docker-up")
        return

    # Load history once per page load (including after F5)
    if "messages" not in st.session_state:
        with st.spinner("Loading conversation history..."):
            st.session_state.messages = _load_history(token)
        st.session_state.history_loaded = True

    # Sidebar — quick actions
    with st.sidebar:
        st.markdown("### Quick analysis")
        ticker = st.text_input("Ticker", value="NVDA", placeholder="AAPL, MSFT...")
        profile = st.selectbox("Risk profile", ["Conservative", "Moderate", "Aggressive"])
        if st.button("Full DD report", type="primary", use_container_width=True):
            st.session_state["pending"] = (
                f"Analyse {ticker.upper()} for a {profile.lower()} investor. "
                "Full Due Diligence report with verdict."
            )
            st.rerun()

        st.divider()
        st.markdown("### Shortcuts")
        shortcuts = {
            "USD/UAH rate": "What is the current USD/UAH exchange rate? Use get_fx_rates, then calculate_irp for 12-month outlook.",
            "US yield curve": "Show me the current US yield curve and recession signal.",
            "US macro snapshot": "Full US macro snapshot: Fed rate, CPI, GDP, yields, VIX, credit spreads.",
        }
        for label, query in shortcuts.items():
            if st.button(label, use_container_width=True):
                st.session_state["pending"] = query
                st.rerun()

        st.divider()
        c_g, c_b = st.columns(2)
        with c_g:
            if st.button("👍", use_container_width=True, help="Good response"):
                st.success("Thanks!")
        with c_b:
            if st.button("👎", use_container_width=True, help="Bad response"):
                st.warning("Noted.")

    # Display conversation history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                _render(msg["content"])
            else:
                st.write(msg["content"])

    # Get user input (from chat box or sidebar shortcut)
    user_input = st.session_state.pop("pending", None) or st.chat_input(
        "Ask anything: stock analysis, FX rates, macro, Kelly sizing..."
    )

    if not user_input:
        if not st.session_state.messages:
            st.info(
                "Examples:\n"
                "  • What is the current USD/UAH rate?\n"
                "  • Analyse NVDA for a conservative investor\n"
                "  • Show me the US yield curve\n"
                "  • Kelly position size: 60% win rate, 2:1 payout"
            )
        return

    # Show user message immediately
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    # Stream and render assistant response
    with st.chat_message("assistant"):
        thinking_ph = st.empty()
        report_ph = st.empty()
        full_text = ""
        t0 = time.time()

        with st.spinner("Fetching live data and reasoning..."):
            for chunk in _stream(token, user_input):
                full_text += chunk
                thinking, output = _split(full_text)

                if thinking and not output:
                    # Show live thinking preview while waiting for output
                    preview = html.escape(thinking[-600:])
                    thinking_ph.markdown(
                        f'<div class="thinking-block">{preview}</div>',
                        unsafe_allow_html=True,
                    )

                if output and len(output) > 60:
                    thinking_ph.empty()
                    report_ph.markdown(
                        f'<div class="report-block">{_clean(output)}</div>',
                        unsafe_allow_html=True,
                    )

        # Final clean render
        thinking_ph.empty()
        report_ph.empty()
        _render(full_text)
        st.caption(f"Completed in {time.time() - t0:.1f}s")

    st.session_state.messages.append({"role": "assistant", "content": full_text})


if __name__ == "__main__":
    main()
