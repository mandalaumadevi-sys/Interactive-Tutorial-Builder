import os

# Tests are hermetic and offline — FORCE the mock LLM and no external services, regardless of
# anything in .env (load_dotenv uses override=False, so these env values win).
os.environ["TB_LLM_MODE"] = "mock"          # no real API calls, no cost
os.environ["OPENROUTER_API_KEY"] = ""       # belt-and-braces: never reach a live key
os.environ["SUPABASE_DB_URL"] = ""          # persistence fails fast → in-memory checkpointer

# If any import/plugin already built a cached Settings before this ran, drop it so the values
# above take effect.
try:
    from tutorial_builder.config import get_settings
    get_settings.cache_clear()
except Exception:  # noqa: BLE001 — package not importable yet is fine
    pass
