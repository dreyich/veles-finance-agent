"""Finance AI Agent — Streamlit Demo UI.

Dark-mode financial dashboard that connects to the FastAPI backend,
streams agent responses in real time, and renders tool output as
structured market-data cards.

Run:
    streamlit run streamlit_app.py
"""

import json
import re
import time
from typing import Generator

import httpx
import streamlit as st

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Finance AI Agent",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Finance AI Agent — powered by LangGraph + yfinance"},
)

# ── Constants ─────────────────────────────────────────────────────────────────
_DEFAULT_API = "http://localhost:8000"
_DEMO_EMAIL = "demo@finance-agent.dev"
_DEMO_PASSWORD = "FinDemo2024!"
_DEMO_USERNAME = "demo_user"
_PAYMENT_TOKEN = "mock_pay_streamlit_demo"
_REQUEST_TIMEOUT = 90.0
_HEALTH_TIMEOUT = 3.0

_EXAMPLE_TICKERS = ["NVDA", "AAPL", "MSFT", "TSLA", "META", "AMZN", "GOOGL", "BRK-B"]

# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
<style>
/* ── Base ── */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0D1117;
    color: #E6EDF3;
}
[data-testid="stSidebar"] {
    background-color: #161B22;
    border-right: 1px solid #30363D;
}
[data-testid="stHeader"] { background-color: #0D1117; }

/* ── Typography ── */
h1, h2, h3 { color: #E6EDF3 !important; letter-spacing: -0.02em; }
p, li, span { color: #C9D1D9; }
code { background: #161B22 !important; color: #79C0FF !important; border-radius: 4px; }

/* ── Inputs ── */
[data-testid="stTextInput"] input,
[data-testid="stChatInput"] textarea {
    background-color: #161B22 !important;
    border: 1px solid #30363D !important;
    color: #E6EDF3 !important;
    border-radius: 8px !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stChatInput"] textarea:focus {
    border-color: #1F6FEB !important;
    box-shadow: 0 0 0 2px rgba(31,111,235,0.2) !important;
}

/* ── Buttons ── */
[data-testid="baseButton-primary"] {
    background-color: #1F6FEB !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    color: #fff !important;
    transition: background 0.15s;
}
[data-testid="baseButton-primary"]:hover {
    background-color: #388BFD !important;
}
[data-testid="baseButton-secondary"] {
    background-color: #21262D !important;
    border: 1px solid #30363D !important;
    border-radius: 8px !important;
    color: #C9D1D9 !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background-color: #161B22;
    border: 1px solid #21262D;
    border-radius: 10px;
    margin-bottom: 8px;
    padding: 4px 8px;
}

/* ── Market data card ── */
.market-card {
    background: #161B22;
    border: 1px solid #30363D;
    border-left: 3px solid #3FB950;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 8px 0;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 13px;
    line-height: 1.65;
    color: #E6EDF3;
    white-space: pre-wrap;
}
.market-card .card-header {
    font-size: 14px;
    font-weight: 700;
    color: #3FB950;
    margin-bottom: 8px;
    border-bottom: 1px solid #30363D;
    padding-bottom: 6px;
}

/* ── Status pill ── */
.status-ok  { color: #3FB950; font-weight: 700; }
.status-err { color: #F85149; font-weight: 700; }
.status-warn{ color: #D29922; font-weight: 700; }

/* ── Ticker pills ── */
.ticker-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.ticker-pill {
    background: #21262D;
    border: 1px solid #30363D;
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 600;
    color: #79C0FF;
    cursor: pointer;
    user-select: none;
}

/* ── Dividers ── */
hr { border-color: #30363D !important; }

/* ── Metric delta ── */
[data-testid="stMetricDelta"] svg { display: none; }
</style>
"""


# ── API helpers ───────────────────────────────────────────────────────────────

def _headers(session_token: str) -> dict:
    return {
        "Authorization": f"Bearer {session_token}",
        "Content-Type": "application/json",
        "X-Payment": _PAYMENT_TOKEN,
    }


def _check_health(base_url: str) -> bool:
    try:
        r = httpx.get(f"{base_url}/health", timeout=_HEALTH_TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


def _register(base_url: str) -> None:
    try:
        httpx.post(
            f"{base_url}/api/v1/auth/register",
            json={"email": _DEMO_EMAIL, "password": _DEMO_PASSWORD, "username": _DEMO_USERNAME},
            timeout=10.0,
        )
    except Exception:
        pass


def _login(base_url: str) -> str | None:
    try:
        r = httpx.post(
            f"{base_url}/api/v1/auth/login",
            data={"email": _DEMO_EMAIL, "password": _DEMO_PASSWORD, "grant_type": "password"},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception:
        return None


def _create_session(base_url: str, user_token: str) -> str | None:
    try:
        r = httpx.post(
            f"{base_url}/api/v1/auth/session",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()["token"]["access_token"]
    except Exception:
        return None


def _ensure_auth(base_url: str) -> bool:
    """Register + login + create session if not already in session_state."""
    if st.session_state.get("session_token"):
        return True

    _register(base_url)
    user_token = _login(base_url)
    if not user_token:
        return False

    session_token = _create_session(base_url, user_token)
    if not session_token:
        return False

    st.session_state["session_token"] = session_token
    return True


def _stream_response(
    base_url: str,
    session_token: str,
    message: str,
) -> Generator[str, None, None]:
    """Yield text chunks from the SSE streaming endpoint."""
    payload = {"messages": [{"role": "user", "content": message}]}
    try:
        with httpx.stream(
            "POST",
            f"{base_url}/api/v1/chatbot/chat/stream",
            headers=_headers(session_token),
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        ) as r:
            r.raise_for_status()
            for raw_line in r.iter_lines():
                line = raw_line.strip()
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if data.get("done"):
                    break
                chunk = data.get("content", "")
                if chunk:
                    yield chunk
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 402:
            yield "\n\n⚠️ **Payment required.** Set `PAYMENT_REQUIRED=false` in `.env.development` to bypass for local dev."
        else:
            yield f"\n\n❌ **API error {exc.response.status_code}:** {exc.response.text[:200]}"
    except Exception as exc:
        yield f"\n\n❌ **Connection error:** {exc}"


# ── FinCoT tag parsing ────────────────────────────────────────────────────────

_THINKING_RE = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL | re.IGNORECASE)
_OUTPUT_RE = re.compile(r"<output>(.*?)</output>", re.DOTALL | re.IGNORECASE)


def _render_fincot(text: str) -> str:
    """Extract <thinking> into expanders and return <output> content (or raw text)."""
    thinking_blocks = _THINKING_RE.findall(text)
    output_blocks = _OUTPUT_RE.findall(text)

    for i, thinking in enumerate(thinking_blocks, start=1):
        label = "Agent Reasoning" if len(thinking_blocks) == 1 else f"Agent Reasoning (step {i})"
        with st.expander(f"🧠 {label}", expanded=False):
            st.markdown(
                f"<div style='font-family:monospace;font-size:13px;"
                f"color:#8B949E;line-height:1.6;white-space:pre-wrap'>"
                f"{thinking.strip()}</div>",
                unsafe_allow_html=True,
            )

    if output_blocks:
        return "\n\n".join(block.strip() for block in output_blocks)

    # No FinCoT tags — strip any partial tags and return as-is
    cleaned = _THINKING_RE.sub("", text)
    cleaned = _OUTPUT_RE.sub("", cleaned)
    return cleaned.strip()


# ── Response rendering ────────────────────────────────────────────────────────

_MARKET_BLOCK_RE = re.compile(
    r"(Market Data Snapshot.*?Source: Yahoo Finance.*?(?=\n\n|\Z))",
    re.DOTALL,
)

_KELLY_BLOCK_RE = re.compile(
    r"(Kelly Criterion Analysis.*?═+)",
    re.DOTALL,
)


def _split_response(text: str) -> list[dict]:
    """Split agent response into prose and tool-output segments."""
    segments: list[dict] = []
    remaining = text

    for pattern, kind in [(_MARKET_BLOCK_RE, "market"), (_KELLY_BLOCK_RE, "kelly")]:
        parts = pattern.split(remaining)
        if len(parts) <= 1:
            continue
        rebuilt: list[dict] = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                if part.strip():
                    rebuilt.append({"type": "prose", "text": part})
            else:
                rebuilt.append({"type": kind, "text": part})
        # Only apply first match to avoid double-splitting
        remaining_segments: list[dict] = []
        for seg in segments if segments else [{"type": "prose", "text": remaining}]:
            if seg["type"] != "prose":
                remaining_segments.append(seg)
                continue
            sub = pattern.split(seg["text"])
            if len(sub) <= 1:
                remaining_segments.append(seg)
            else:
                for j, s in enumerate(sub):
                    if j % 2 == 0:
                        if s.strip():
                            remaining_segments.append({"type": "prose", "text": s})
                    else:
                        remaining_segments.append({"type": kind, "text": s})
        segments = remaining_segments
        break

    if not segments:
        segments = [{"type": "prose", "text": text}]

    return segments


def _render_response(text: str) -> None:
    """Render the full agent response: FinCoT expander + tool cards + prose."""
    # 1. Extract <thinking> into expanders; get cleaned output text
    display_text = _render_fincot(text)

    # 2. Split remaining text into prose / tool-card segments
    segments = _split_response(display_text)

    for seg in segments:
        if seg["type"] == "prose":
            st.markdown(seg["text"])
        elif seg["type"] in ("market", "kelly"):
            lines = seg["text"].strip().split("\n")
            header = lines[0] if lines else "Tool Output"
            body = "\n".join(lines[1:]) if len(lines) > 1 else seg["text"]
            st.markdown(
                f'<div class="market-card">'
                f'<div class="card-header">📊 {header}</div>'
                f"{body}"
                f"</div>",
                unsafe_allow_html=True,
            )


def _portfolio_context() -> str:
    balance = st.session_state.get("portfolio_balance")
    risk = st.session_state.get("risk_profile", "Moderate")
    parts = []
    if balance:
        parts.append(f"My portfolio balance is ${balance:,.2f} USD.")
    if risk:
        parts.append(f"My risk profile is {risk.lower()}.")
    return (" ".join(parts) + " ") if parts else ""


def _ticker_query(ticker: str) -> str:
    ctx = _portfolio_context()
    return (
        f"{ctx}Use the get_market_data tool to fetch a full snapshot for **{ticker.upper()}**. "
        "Then give me a concise analyst-style summary: valuation vs sector peers, "
        "key risks from the news, and your read on the analyst consensus."
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar() -> str:
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        base_url = st.text_input(
            "API Base URL",
            value=st.session_state.get("base_url", _DEFAULT_API),
            key="api_url_input",
        )
        if base_url != st.session_state.get("base_url"):
            st.session_state["base_url"] = base_url
            st.session_state.pop("session_token", None)
            st.session_state.pop("api_healthy", None)
            st.rerun()

        # Health status
        st.markdown("---")
        st.markdown("**Connection**")
        healthy = st.session_state.get("api_healthy")
        if healthy is True:
            st.markdown('<p class="status-ok">● Connected</p>', unsafe_allow_html=True)
        elif healthy is False:
            st.markdown('<p class="status-err">● Offline</p>', unsafe_allow_html=True)
            st.caption("Start the server: `make dev`")
        else:
            st.markdown('<p class="status-warn">● Checking…</p>', unsafe_allow_html=True)

        if st.button("Refresh", use_container_width=True):
            st.session_state.pop("api_healthy", None)
            st.session_state.pop("session_token", None)
            st.rerun()

        # Auth status
        if st.session_state.get("session_token"):
            st.markdown('<p class="status-ok">● Authenticated</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p class="status-err">● Not authenticated</p>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("**Portfolio Settings**")

        portfolio_balance = st.number_input(
            "Portfolio Balance (USD)",
            min_value=0.0,
            max_value=100_000_000.0,
            value=float(st.session_state.get("portfolio_balance", 10_000.0)),
            step=1_000.0,
            format="%.2f",
            key="portfolio_balance_input",
        )
        if portfolio_balance != st.session_state.get("portfolio_balance"):
            st.session_state["portfolio_balance"] = portfolio_balance

        risk_profile = st.selectbox(
            "Risk Profile",
            options=["Conservative", "Moderate", "Aggressive"],
            index=["Conservative", "Moderate", "Aggressive"].index(
                st.session_state.get("risk_profile", "Moderate")
            ),
            key="risk_profile_input",
        )
        if risk_profile != st.session_state.get("risk_profile"):
            st.session_state["risk_profile"] = risk_profile

        st.markdown("---")
        st.markdown("**Quick Tickers**")
        pill_html = '<div class="ticker-row">'
        for t in _EXAMPLE_TICKERS:
            pill_html += f'<span class="ticker-pill">{t}</span>'
        pill_html += "</div>"
        st.markdown(pill_html, unsafe_allow_html=True)
        st.caption("Type any ticker in the analysis bar above.")

        st.markdown("---")
        if st.button("🗑️ Clear chat", use_container_width=True):
            st.session_state["messages"] = []
            st.rerun()

        st.markdown("---")
        st.markdown(
            "<small style='color:#484F58'>Finance AI Agent · LangGraph + yfinance<br/>"
            "Data: Yahoo Finance · Not financial advice</small>",
            unsafe_allow_html=True,
        )

    return base_url


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    # Initialise session state defaults
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("base_url", _DEFAULT_API)
    st.session_state.setdefault("api_healthy", None)

    base_url = _render_sidebar()

    # ── Header ────────────────────────────────────────────────────────────────
    col_title, col_status = st.columns([6, 1])
    with col_title:
        st.markdown("# 📈 Finance AI Agent")
        st.markdown(
            "<p style='color:#484F58;margin-top:-12px;'>Real-time market data · Powered by LangGraph</p>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Health check (runs once per session) ─────────────────────────────────
    if st.session_state["api_healthy"] is None:
        with st.spinner("Connecting to API…"):
            st.session_state["api_healthy"] = _check_health(base_url)
        st.rerun()

    if not st.session_state["api_healthy"]:
        st.error(
            "**Cannot reach the FastAPI backend.**  \n"
            f"Make sure the server is running at `{base_url}`  \n"
            "Start it with: `make dev`  or  `docker-compose up`"
        )
        return

    # ── Auth ──────────────────────────────────────────────────────────────────
    if not _ensure_auth(base_url):
        st.error("Authentication failed. Check that the API server is running and the database is healthy.")
        return

    # ── Quick Ticker Analysis ─────────────────────────────────────────────────
    st.markdown("#### Quick Analysis")
    ticker_col, btn_col = st.columns([4, 1])
    with ticker_col:
        ticker_input = st.text_input(
            "ticker_input",
            placeholder="Enter ticker symbol — e.g. NVDA, AAPL, TSLA",
            label_visibility="collapsed",
            key="ticker_field",
        )
    with btn_col:
        analyze_clicked = st.button("Analyze →", type="primary", use_container_width=True)

    if analyze_clicked and ticker_input.strip():
        prompt = _ticker_query(ticker_input.strip())
        st.session_state["messages"].append({"role": "user", "content": prompt})
        st.session_state["pending_prompt"] = prompt

    st.markdown("---")

    # ── Chat history ──────────────────────────────────────────────────────────
    for msg in st.session_state["messages"]:
        avatar = "🧑‍💼" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            if msg["role"] == "assistant":
                _render_response(msg["content"])
            else:
                st.markdown(msg["content"])

    # ── Free-form chat input ──────────────────────────────────────────────────
    free_prompt = st.chat_input("Ask the agent anything — markets, strategies, analysis…")
    if free_prompt:
        ctx = _portfolio_context()
        enriched = f"{ctx}{free_prompt}" if ctx else free_prompt
        st.session_state["messages"].append({"role": "user", "content": free_prompt})
        st.session_state["pending_prompt"] = enriched

    # ── Stream response for any pending prompt ────────────────────────────────
    pending = st.session_state.pop("pending_prompt", None)
    if pending:
        session_token = st.session_state["session_token"]

        with st.chat_message("user", avatar="🧑‍💼"):
            st.markdown(pending)

        with st.chat_message("assistant", avatar="🤖"):
            # Show thinking indicator while waiting for first token
            thinking_placeholder = st.empty()
            thinking_placeholder.markdown(
                "<p style='color:#484F58;font-style:italic;'>⏳ Thinking…</p>",
                unsafe_allow_html=True,
            )

            accumulated = ""
            stream_placeholder = st.empty()

            for chunk in _stream_response(base_url, session_token, pending):
                if accumulated == "" and thinking_placeholder:
                    thinking_placeholder.empty()
                accumulated += chunk
                stream_placeholder.markdown(accumulated + "▌")

            # Final render: remove cursor, apply rich formatting
            stream_placeholder.empty()
            _render_response(accumulated)

        st.session_state["messages"].append({"role": "assistant", "content": accumulated})
        st.rerun()


if __name__ == "__main__":
    main()
