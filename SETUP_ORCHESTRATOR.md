# Setup Instructions: Upgraded Orchestrator & Web Search

## What Changed

Three major improvements have been made to the Finance AI agent:

1. **Added Web Search tool** - can now answer questions about cryptocurrencies, commodities, economic indicators, and recent news
2. **Upgraded orchestrator to llama-3.1-70b** - much smarter reasoning and better tool selection
3. **Using Groq API** - free (with rate limits), no cold start, no separate pod needed

## API Keys Required

### 1. Groq API Key (Required for production)

**Free tier limits:**
- 30 requests/minute
- 6,000 tokens/minute for llama-3.1-70b
- No credit card needed

**Get your key:**
1. Go to https://console.groq.com
2. Sign up (free)
3. Navigate to API Keys
4. Create new key
5. Copy the key (starts with `gsk_...`)

**Set it in RunPod Serverless environment:**
```
ORCHESTRATOR_API_KEY=gsk_YOUR_KEY_HERE
```

### 2. Tavily API Key (Optional - for better web search)

**Free tier:**
- 1,000 searches/month
- No credit card needed

**Get your key:**
1. Go to https://tavily.com
2. Sign up (free)
3. Get API key from dashboard
4. Copy the key (starts with `tvly-...`)

**Set it in RunPod Serverless environment:**
```
TAVILY_API_KEY=tvly_YOUR_KEY_HERE
```

**Note:** If Tavily is not configured, web search will fall back to DuckDuckGo (slower, less reliable, but free and requires no API key).

## RunPod Serverless Environment Variables

Update your RunPod Serverless endpoint with these variables:

```bash
# Veles model (unchanged)
VELES_BASE_URL=http://localhost:30000/v1
VELES_MODEL=veles-finance-7b
VELES_API_KEY=EMPTY

# Groq orchestrator (NEW - replaces RunPod orchestrator pod)
ORCHESTRATOR_BASE_URL=https://api.groq.com/openai/v1
ORCHESTRATOR_MODEL=llama-3.1-70b-versatile
ORCHESTRATOR_API_KEY=gsk_YOUR_GROQ_KEY_HERE

# Tavily web search (OPTIONAL - falls back to DuckDuckGo if not set)
TAVILY_API_KEY=tvly_YOUR_TAVILY_KEY_HERE
```

## What This Enables

### Before (without web search):
- ✅ Stock prices and fundamentals
- ✅ SEC 10-K reports
- ✅ Currency exchange rates (fiat only)
- ❌ Cryptocurrency prices
- ❌ Commodity prices (gold, oil, etc.)
- ❌ Economic indicators (inflation, GDP, unemployment)
- ❌ Recent news beyond Yahoo Finance

### After (with web search):
- ✅ Everything above, plus:
- ✅ "What's Bitcoin price today?" → web_search
- ✅ "Current gold price per ounce?" → web_search
- ✅ "US inflation rate 2026?" → web_search
- ✅ "Latest Tesla earnings news?" → web_search
- ✅ "Ethereum market cap?" → web_search

## Cost Impact

**Before:**
- Fly.io gateway: ~$5-10/month
- RunPod orchestrator pod: ~$20-30/month (always-on)
- RunPod Veles serverless: pay-per-use

**After:**
- Fly.io gateway: ~$5-10/month (unchanged)
- Groq orchestrator: **$0** (free tier)
- RunPod Veles serverless: pay-per-use (unchanged)
- Tavily web search: **$0** (1000 searches/month free)

**Net savings: ~$20-30/month** by eliminating the orchestrator pod!

## Testing Locally

To test the web search locally (with DuckDuckGo fallback):

```bash
pip install duckduckgo-search
python -c "from agent.tools import web_search; print(web_search.invoke({'query': 'Bitcoin price today'}))"
```

## Rate Limits & Fallbacks

**Groq limits (llama-3.1-70b):**
- 30 requests/minute = 1,800 requests/hour
- If exceeded: automatic throttling (requests wait, don't fail)
- For typical usage: limits are very generous

**Tavily limits:**
- 1,000 searches/month on free tier
- If exceeded: falls back to DuckDuckGo automatically
- For production with >1000 searches/month: upgrade to Tavily paid ($1/1000 searches)

**Web search fallback chain:**
1. Try Tavily (if TAVILY_API_KEY is set)
2. Fall back to DuckDuckGo (if Tavily fails or not configured)
3. Return error only if both fail

## Deployment Checklist

- [ ] Get Groq API key from https://console.groq.com
- [ ] (Optional) Get Tavily API key from https://tavily.com
- [ ] Update RunPod Serverless environment variables
- [ ] Deploy updated code to RunPod
- [ ] Test: ask "What's Bitcoin price?" - should use web_search
- [ ] Test: ask "What's AAPL price?" - should use get_market_data (not web search)
- [ ] Monitor Groq rate limits in first week

## Monitoring

Watch the orchestrator startup log for confirmation:
```
[orchestrator] base_url=https://api.groq.com/openai/v1 model=llama-3.1-70b-versatile
```

If you see `llama3.2:3b` instead, the env vars didn't load correctly.
