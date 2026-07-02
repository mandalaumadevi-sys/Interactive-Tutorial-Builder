# Always-on FastAPI + LangGraph server for Tuti (Render / Railway / Fly / any container host).
# NOTE: this is NOT for Vercel — the server runs long background builds + SSE + in-memory state,
# which serverless can't host. Deploy it on an always-on service and point the frontend at its URL.
FROM python:3.12-slim

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1

# Copy the whole backend (src/ + templates/ + eval-sets/ + reference_animations/ + prompts + skills).
COPY . /app

# Editable install so the packaged prompt/skill .md files are read from the source tree at runtime.
RUN pip install -e .

# Sensible production defaults (secrets + model overrides are supplied as env vars by the host).
ENV TB_LLM_MODE=real \
    TB_LLM_PROVIDER=openrouter

EXPOSE 8000
# The host injects $PORT; bind 0.0.0.0 so it's reachable.
CMD ["sh", "-c", "tutorial-builder serve --host 0.0.0.0 --port ${PORT:-8000}"]
