from __future__ import annotations
import asyncio
import json
import os
import pathlib
import re
import uuid
import uvicorn
from datetime import datetime
from typing import Literal

import yfinance as yf
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from langchain_core.messages import HumanMessage
from openai import OpenAI
from pydantic import BaseModel, Field
from agent.graph import graph as langgraph_agent
from agent.sec_tool import fetch_sec_10k, format_sec_report

if os.getenv("SENTRY_DSN"):
    import sentry_sdk
    sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), environment=os.getenv("SENTRY_ENVIRONMENT", "production"))

# WORM audit logging — the local traces.jsonl file (below) is append-only in
# practice but not immutable: anyone with volume access can edit or delete
# past entries. S3 Object Lock (governance/compliance mode) makes each trace
# genuinely un-editable/un-deletable for its retention period, which matters
# for SEC-style audit requirements. Inactive unless AUDIT_S3_BUCKET is set —
# safe to ship before that bucket exists.
_AUDIT_S3_BUCKET = os.getenv("AUDIT_S3_BUCKET")


def _upload_trace_worm(trace: dict) -> None:
    if not _AUDIT_S3_BUCKET:
        return
    try:
        import boto3
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        key = f"traces/{trace['ts']}_{uuid.uuid4().hex[:8]}.json"
        put_kwargs = {
            "Bucket": _AUDIT_S3_BUCKET,
            "Key": key,
            "Body": json.dumps(trace).encode("utf-8"),
            "ContentType": "application/json",
        }
        # Object Lock requires the bucket to have it enabled; retention mode/
        # period are only sent if explicitly configured, so this doesn't
        # break on a bucket that hasn't set up Object Lock yet.
        retain_days = os.getenv("AUDIT_S3_RETENTION_DAYS")
        if retain_days:
            from datetime import timedelta
            put_kwargs["ObjectLockMode"] = os.getenv("AUDIT_S3_LOCK_MODE", "COMPLIANCE")
            put_kwargs["ObjectLockRetainUntilDate"] = datetime.utcnow() + timedelta(days=int(retain_days))
        s3.put_object(**put_kwargs)
    except Exception:
        pass  # audit logging must never break the actual user-facing request


# ── App & client ──────────────────────────────────────────────────────────────

api = FastAPI(title="Veles Finance Agent", version="2.4.0")
api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_STATIC = pathlib.Path(__file__).parent / "static"
if _STATIC.exists():
    api.mount("/ui", StaticFiles(directory=str(_STATIC), html=True), name="static")

@api.get("/")
def root():
    idx = _STATIC / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return {"status": "ok", "ui": "/ui", "docs": "/docs"}

_VELES_BASE = os.getenv("VELES_BASE_URL", "http://localhost:11434/v1")
_VELES_MODEL = os.getenv("VELES_MODEL", "veles")
_ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "llama3.2:3b")

client = OpenAI(base_url=_VELES_BASE, api_key=os.getenv("VELES_API_KEY", "ollama"))

_WARM_PROMPT = os.getenv("WARM_PROMPT", "Hi")

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class DueDiligenceResponse(BaseModel):
    verdict: Literal["APPROVED", "REJECTED"]
    ticker: str
    risk_profile: str
    key_factors: list[str] = Field(description="2-3 main reasons for the verdict")
    analysis: str = Field(description="Detailed qualitative analysis")
    max_position: str = Field(description="Recommended max portfolio allocation")
    raw_data: str = Field(description="Raw market data used")

class KellyResponse(BaseModel):
    full_kelly_pct: float
    half_kelly_pct: float
    analysis: str

class GenericResponse(BaseModel):
    response: str

class SecResponse(BaseModel):
    ticker: str
    filing_date: str | None = None
    accession: str | None = None
    edgar_url: str | None = None
    financials: dict | None = None
    report: str
    error: str | None = None

# ── Helpers ───────────────────────────────────────────────────────────────────

_MARKET_CAP_LABELS = [(1_000_000_000_000, "T"), (1_000_000_000, "B"), (1_000_000, "M")]
def _fmt_cap(v): return "N/A" if v is None else next((f"${v/t:.2f}{s}" for t,s in _MARKET_CAP_LABELS if abs(v)>=t), f"${v:,.0f}")
def _fmt_price(v): return f"${v:,.2f}" if v is not None else "N/A"
def _fmt_ratio(v, d=2): return f"{v:.{d}f}" if v is not None else "N/A"

_THRESHOLDS = {
    "conservative": {"max_pe": 25, "max_beta": 1.0, "max_position": "5%"},
    "moderate":     {"max_pe": 35, "max_beta": 1.4, "max_position": "10%"},
    "aggressive":   {"max_pe": 60, "max_beta": 2.0, "max_position": "20%"},
}

# ── Tool: Due Diligence (deterministic verdict) ───────────────────────────────

def _fetch_market_data(ticker: str) -> dict:
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}

def run_due_diligence(ticker: str, risk_profile: str) -> DueDiligenceResponse:
    ticker = ticker.strip().upper()
    profile = risk_profile.lower()
    thr = _THRESHOLDS.get(profile, _THRESHOLDS["moderate"])
    info = _fetch_market_data(ticker)

    company = info.get("longName") or ticker
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    pe = info.get("trailingPE")
    beta = info.get("beta")
    profit_margin = info.get("profitMargins")
    target = info.get("targetMeanPrice")
    market_cap = info.get("marketCap")
    revenue = info.get("totalRevenue")
    rec = (info.get("recommendationKey") or "N/A").upper()

    # ── Deterministic verdict (same logic as fine-tuning training data) ──
    rejects, approves = [], []
    if pe is not None:
        if pe > thr["max_pe"]:
            rejects.append(f"P/E {pe:.1f}x exceeds {profile} threshold of {thr['max_pe']}x")
        else:
            approves.append(f"P/E {pe:.1f}x within {profile} threshold ({thr['max_pe']}x)")
    if beta is not None:
        if beta > thr["max_beta"]:
            rejects.append(f"Beta {beta:.2f} exceeds {profile} ceiling of {thr['max_beta']}")
        else:
            approves.append(f"Beta {beta:.2f} within {profile} tolerance")
    if profit_margin is not None:
        if profit_margin < 0:
            rejects.append(f"Negative profit margin ({profit_margin*100:.1f}%)")
        elif profit_margin > 0.15:
            approves.append(f"Strong margin {profit_margin*100:.1f}%")
    if target and price and target > price * 1.15:
        approves.append(f"Analyst target {_fmt_price(target)} implies {((target/price)-1)*100:.0f}% upside")

    verdict: Literal["APPROVED", "REJECTED"] = "REJECTED" if rejects else "APPROVED"
    key_factors = (rejects if rejects else approves)[:3]

    # ── Raw data summary ──
    raw_data = (
        f"{company} ({ticker}) | Price: {_fmt_price(price)} | "
        f"Market Cap: {_fmt_cap(market_cap)} | Revenue: {_fmt_cap(revenue)} | "
        f"P/E: {_fmt_ratio(pe)} | Beta: {_fmt_ratio(beta)} | "
        f"Margin: {_fmt_ratio(profit_margin*100, 1) if profit_margin else 'N/A'}% | "
        f"Analyst: {rec} | Target: {_fmt_price(target)}"
    )

    # ── Ask model for qualitative analysis (not for verdict!) ──
    analysis_prompt = f"""You are Veles, a professional financial analyst.
{company} ({ticker}) | Profile: {profile} | Verdict: {verdict}
Data: {raw_data}
Key factors: {'; '.join(key_factors)}
Write exactly 2 sentences explaining the verdict. Be direct and professional."""

    try:
        resp = client.chat.completions.create(
            model=_VELES_MODEL,
            messages=[{"role": "user", "content": analysis_prompt}],
            max_tokens=120,
        )
        analysis = resp.choices[0].message.content or ""
    except Exception as e:
        analysis = f"{verdict}: {'; '.join(key_factors)}"

    return DueDiligenceResponse(
        verdict=verdict,
        ticker=ticker,
        risk_profile=profile,
        key_factors=key_factors,
        analysis=analysis,
        max_position=thr["max_position"],
        raw_data=raw_data,
    )


# ── Tool: Market Data ─────────────────────────────────────────────────────────

def get_market_data(ticker: str) -> str:
    ticker = ticker.strip().upper()
    info = _fetch_market_data(ticker)
    if not info:
        return f"No data for {ticker}"
    company = info.get("longName") or ticker
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev = info.get("previousClose")
    change = "N/A"
    if price and prev:
        d = price - prev; pct = (d/prev)*100; sign = "+" if d >= 0 else ""
        change = f"{sign}{d:.2f} ({sign}{pct:.2f}%)"
    news = info.get("news") or []
    news_lines = []
    for i, item in enumerate(news[:3], 1):
        c = item.get("content") or {}
        title = c.get("title") or item.get("title") or "(no title)"
        news_lines.append(f"  {i}. {title}")
    return (
        f"Market Data — {company} ({ticker})\n"
        f"Price: {_fmt_price(price)} | Change: {change}\n"
        f"Market Cap: {_fmt_cap(info.get('marketCap'))} | P/E: {_fmt_ratio(info.get('trailingPE'))} | Beta: {_fmt_ratio(info.get('beta'))}\n"
        f"Revenue: {_fmt_cap(info.get('totalRevenue'))} | Margin: {_fmt_ratio(info.get('profitMargins',0)*100,1) if info.get('profitMargins') else 'N/A'}%\n"
        f"Analyst: {(info.get('recommendationKey') or 'N/A').upper()} | Target: {_fmt_price(info.get('targetMeanPrice'))}\n"
        f"Recent News:\n" + ("\n".join(news_lines) or "  No recent news.")
    )


# ── Tool: Kelly ───────────────────────────────────────────────────────────────

def kelly_position_size(win_probability: float, payout_ratio: float) -> KellyResponse:
    p, b = win_probability, payout_ratio
    edge = p * b - (1 - p)
    if edge <= 0:
        return KellyResponse(full_kelly_pct=0, half_kelly_pct=0,
                             analysis=f"No positive edge (EV={edge:.4f}). Do not risk capital.")
    kelly = edge / b
    analysis_prompt = f"""Kelly Criterion result: win rate={p:.1%}, payout={b:.2f}x, expected value=+{edge:.4f}.
Full Kelly = {kelly*100:.2f}%, Half Kelly = {kelly*100/2:.2f}%.
Explain in 2 sentences what this means for position sizing and whether to use full or half Kelly."""
    try:
        resp = client.chat.completions.create(
            model=_VELES_MODEL,
            messages=[{"role": "user", "content": analysis_prompt}],
        )
        analysis = resp.choices[0].message.content or ""
    except Exception:
        analysis = f"Full Kelly: {kelly*100:.2f}%. Half Kelly recommended for live trading."
    return KellyResponse(full_kelly_pct=round(kelly*100, 2),
                         half_kelly_pct=round(kelly*100/2, 2), analysis=analysis)


# ── Routing ───────────────────────────────────────────────────────────────────

def _extract_ticker(text: str) -> str | None:
    known = {"NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AMD",
             "INTC", "NFLX", "BRK", "JPM", "BAC", "KO", "JNJ", "GME", "RIVN",
             "PLTR", "SPY", "COIN", "BRKB"}
    # Handle BRK-B → BRKB
    text = text.replace("BRK-B", "BRKB").replace("BRK.B", "BRKB")
    tickers = re.findall(r'\b([A-Z]{1,5})\b', text.upper())
    for t in tickers:
        if t in known:
            return "BRK-B" if t == "BRKB" else t
    return tickers[0] if tickers else None

def _extract_risk(text: str) -> str:
    t = text.lower()
    if "conserv" in t: return "conservative"
    if "aggress" in t: return "aggressive"
    return "moderate"


# ── API endpoints ─────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    message: str

class AgentRequest(BaseModel):
    message: str
    history: list[dict] = []  # optional prior turns: [{"role": "user/assistant", "content": "..."}]

class AgentResponse(BaseModel):
    answer: str
    tools_used: list[str]
    steps: int

@api.get("/ping")
def ping():
    return "OK"

@api.post("/warm")
async def warm():
    """Pre-warming endpoint — called by frontend on page load to eliminate cold start."""
    try:
        resp = client.chat.completions.create(
            model=_VELES_MODEL,
            messages=[{"role": "user", "content": _WARM_PROMPT}],
            max_tokens=1,
        )
        return {"status": "warm", "model": _VELES_MODEL}
    except Exception as e:
        return {"status": "warming", "detail": str(e)}

@api.get("/health")
def health():
    return {
        "status": "ok",
        "orchestrator": _ORCHESTRATOR_MODEL,
        "extractor": _VELES_MODEL,
        "veles_backend": _VELES_BASE,
        "version": "2.4.0",
    }

@api.post("/due-diligence", response_model=DueDiligenceResponse)
async def due_diligence(ticker: str, risk_profile: str = "moderate"):
    return run_due_diligence(ticker, risk_profile)

@api.post("/sec", response_model=SecResponse)
async def sec_10k(ticker: str):
    """Fetch the latest 10-K annual report from SEC EDGAR and extract key financials."""
    data = fetch_sec_10k(ticker.strip().upper())
    return SecResponse(
        ticker=data.get("ticker", ticker),
        filing_date=data.get("filing_date"),
        accession=data.get("accession"),
        edgar_url=data.get("edgar_url"),
        financials=data.get("financials"),
        report=format_sec_report(data),
        error=data.get("error"),
    )

@api.post("/kelly", response_model=KellyResponse)
async def kelly(win_probability: float, payout_ratio: float):
    return kelly_position_size(win_probability, payout_ratio)

@api.post("/ask")
async def ask(req: AskRequest):
    msg = req.message
    msg_lower = msg.lower()

    if any(w in msg_lower for w in ["due diligence", "dd ", "analyse", "analyze", "suitable", "аналіз"]):
        ticker = _extract_ticker(msg)
        if ticker:
            result = run_due_diligence(ticker, _extract_risk(msg))
            return result.model_dump()

    if any(w in msg_lower for w in ["10-k", "10k", "annual report", "sec", "edgar", "filing", "річний звіт"]):
        ticker = _extract_ticker(msg)
        if ticker:
            data = fetch_sec_10k(ticker)
            return {"response": format_sec_report(data)}

    if any(w in msg_lower for w in ["price", "market data", "stock", "ціна"]):
        ticker = _extract_ticker(msg)
        if ticker:
            return {"response": get_market_data(ticker)}

    if "kelly" in msg_lower:
        nums = [float(x) for x in re.findall(r'\d+\.?\d*', msg)]
        if len(nums) >= 2:
            return kelly_position_size(nums[0]/100 if nums[0] > 1 else nums[0], nums[1]).model_dump()

    # Generic question
    resp = client.chat.completions.create(
        model=_VELES_MODEL,
        messages=[
            {"role": "system", "content": "You are Veles, a professional financial analyst AI. Answer concisely and professionally."},
            {"role": "user", "content": msg},
        ],
    )
    return {"response": resp.choices[0].message.content or ""}


@api.post("/agent", response_model=AgentResponse)
async def agent_chat(req: AgentRequest):
    """Full LangGraph agent: orchestrator (llama3.2:3b) routes to tools, Veles extracts data.

    Supports all 4 tools: market data, due diligence, Kelly criterion, SEC 10-K.
    """
    from langchain_core.messages import AIMessage, HumanMessage as LCHuman, SystemMessage

    # Build message history (prior turns + current message)
    messages: list = []
    for h in req.history:
        role = h.get("role", "")
        content = h.get("content", "")
        if role == "user":
            messages.append(LCHuman(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(LCHuman(content=req.message))

    # Run the agent graph
    result = langgraph_agent.invoke({"messages": messages})

    # Extract answer and tool usage from message history
    tools_used = []
    final_answer = ""
    steps = 0

    for m in result["messages"]:
        if isinstance(m, SystemMessage):
            continue
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                tools_used.append(tc["name"])
            steps += 1
        if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            c = m.content
            if isinstance(c, list):
                final_answer = "".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in c
                )
            else:
                final_answer = c

    response = AgentResponse(
        answer=final_answer or "Analysis complete. See tool results above.",
        tools_used=list(dict.fromkeys(tools_used)),
        steps=steps,
    )

    # Async trace logging — non-blocking. Written to the network volume
    # (persists across worker restarts) instead of the ephemeral container disk.
    trace = {
        "ts": datetime.utcnow().isoformat(),
        "q": req.message,
        "tools": response.tools_used,
        "steps": response.steps,
        "a": response.answer[:500],
    }
    _traces_path = pathlib.Path(os.getenv("TRACES_PATH", "/runpod-volume/traces.jsonl"))
    asyncio.create_task(
        asyncio.to_thread(
            lambda: _traces_path.open("a", encoding="utf-8").write(json.dumps(trace) + "\n")
        )
    )
    asyncio.create_task(asyncio.to_thread(_upload_trace_worm, trace))

    return response


if __name__ == "__main__":
    uvicorn.run("main:api", host="0.0.0.0", port=3003, reload=False)
