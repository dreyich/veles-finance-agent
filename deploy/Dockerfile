FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt* ./
RUN pip install --no-cache-dir \
    fastapi uvicorn httpx openai \
    yfinance langchain-openai langgraph \
    pydantic 2>/dev/null || true

COPY . .

EXPOSE 3003

CMD ["python", "main.py"]
