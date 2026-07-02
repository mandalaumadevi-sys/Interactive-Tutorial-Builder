"""Runtime configuration, loaded from environment / .env.

A single cached ``Settings`` object is the source of truth for models, thresholds,
generation counts, and resolved filesystem paths used across the pipeline.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = NEW PROJECT/  (config.py → tutorial_builder → src → root)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")

# Packaged prompts/skills live next to the code; data assets live at the project root.
_PACKAGE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # ---- OpenRouter (OpenAI-compatible) ----
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_app_title: str = Field(default="Tutorial Builder", alias="OPENROUTER_APP_TITLE")
    openrouter_http_referer: str = Field(default="http://localhost", alias="OPENROUTER_HTTP_REFERER")

    # ---- Provider switch: openrouter | gemini ----
    # 'gemini' routes every call to Google's OpenAI-compatible Gemini endpoint using GEMINI_API_KEY
    # and TB_GEMINI_MODEL. Flip back to 'openrouter' (the default) with one env change.
    llm_provider: str = Field(default="openrouter", alias="TB_LLM_PROVIDER")

    # ---- Models (text + vision + judge) — OpenRouter path ----
    text_model: str = Field(default="anthropic/claude-sonnet-4.6", alias="TB_TEXT_MODEL")
    vision_model: str = Field(default="anthropic/claude-sonnet-4.6", alias="TB_VISION_MODEL")
    judge_model: str = Field(default="anthropic/claude-sonnet-4.6", alias="TB_JUDGE_MODEL")

    # ---- Gemini (Google AI) — used when llm_provider == 'gemini' ----
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/", alias="GEMINI_BASE_URL")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="TB_GEMINI_MODEL")

    # ---- Generation config ----
    mcq_per_block: int = Field(default=2, alias="TB_MCQ_PER_BLOCK")
    mcq_min: int = Field(default=2, alias="TB_MCQ_MIN")
    mcq_max: int = Field(default=3, alias="TB_MCQ_MAX")
    final_assessment_count: int = Field(default=5, alias="TB_FINAL_ASSESSMENT_COUNT")

    # Block-division target (the divider groups source sections into this many blocks)
    min_blocks: int = Field(default=4, alias="TB_MIN_BLOCKS")
    max_blocks: int = Field(default=5, alias="TB_MAX_BLOCKS")

    # Cap vision image-description calls at ingest (decks can have 100+ images → slow/expensive).
    # Only the most likely concept images are vision-described; the rest use a free heuristic.
    max_vision_describe: int = Field(default=10, alias="TB_MAX_VISION_DESCRIBE")
    # Per-LLM-call timeout (seconds) so a slow/hanging request can never stall a run forever.
    llm_timeout: float = Field(default=90.0, alias="TB_LLM_TIMEOUT")

    pass_threshold: float = Field(default=7.0, alias="TB_PASS_THRESHOLD")
    max_refine_attempts: int = Field(default=1, alias="TB_MAX_REFINE_ATTEMPTS")
    # 2 → the source-grounded self-check can fix once AND re-verify the fix (1 would fix without
    # re-checking). Keeps Agent 1 content strictly inside the PPT/material.
    self_validate_retries: int = Field(default=2, alias="TB_SELF_VALIDATE_RETRIES")
    temperature: float = Field(default=0.2, alias="TB_TEMPERATURE")

    # ---- LLM mode: real | mock ----
    llm_mode: str = Field(default="real", alias="TB_LLM_MODE")

    # ---- Supabase Postgres: the SINGLE persistence backend (no SQLite/local) ----
    # Full connection URI from Supabase → Project Settings → Database → Connection string → URI.
    # Use the Session pooler or Direct connection; the Transaction pooler also works because we
    # disable prepared statements (prepare_threshold=0).
    supabase_db_url: str = Field(default="", alias="SUPABASE_DB_URL")
    db_pool_max: int = Field(default=10, alias="TB_DB_POOL_MAX")

    # ---- Display: USD→INR rate for the cost panel (OpenRouter bills in USD) ----
    usd_to_inr: float = Field(default=88.0, alias="TB_USD_TO_INR")

    # ---- Prompt caching: mark the stable system prompt with cache_control so the large
    #      shared prefix is cached across calls (Anthropic/Claude via OpenRouter is opt-in). ----
    prompt_cache: bool = Field(default=True, alias="TB_PROMPT_CACHE")

    # ---- Paths (relative to project root unless absolute). Note: course memory, the cost
    #      ledger, and run metadata now live in Supabase Postgres, NOT on disk. Only true file
    #      artifacts (input decks, extracted images, drafts, published tutorials) use the disk. ----
    runs_dir: str = Field(default="runs", alias="TB_RUNS_DIR")
    # Canonical library of finished tutorials (<course>/<session>.html). Empty default →
    # repo top level (beside backend/ and frontend/), not inside backend/.
    generated_tutorials_dir: str = Field(default="", alias="TB_GENERATED_TUTORIALS_DIR")
    templates_dir: str = Field(default="templates", alias="TB_TEMPLATES_DIR")
    eval_sets_dir: str = Field(default="eval-sets", alias="TB_EVAL_SETS_DIR")
    mcq_prompt_path: str = Field(
        default="prompts/MCQ_generator_prompt.md", alias="TB_MCQ_PROMPT_PATH"
    )
    block_division_prompt_path: str = Field(
        default="prompts/Block_division.md", alias="TB_BLOCK_DIVISION_PROMPT_PATH"
    )

    # ---- provider resolution ----
    @property
    def is_gemini(self) -> bool:
        return self.llm_provider.strip().lower() == "gemini"

    @property
    def active_base_url(self) -> str:
        return self.gemini_base_url if self.is_gemini else self.openrouter_base_url

    @property
    def active_api_key(self) -> str:
        return self.gemini_api_key if self.is_gemini else self.openrouter_api_key

    def _text(self) -> str:
        return self.gemini_model if self.is_gemini else self.text_model

    # ---- per-stage model resolution (Gemini uses one model for every stage) ----
    @property
    def divider_model(self) -> str:
        return self._text()

    @property
    def agent1_model(self) -> str:
        return self._text()

    @property
    def agent2_model(self) -> str:  # vision (Gemini is multimodal)
        return self.gemini_model if self.is_gemini else self.vision_model

    @property
    def mcq_model(self) -> str:
        return self._text()

    @property
    def assessment_model(self) -> str:
        return self._text()

    @property
    def eval_model(self) -> str:
        return self.gemini_model if self.is_gemini else self.judge_model

    # ---- toggles ----
    @property
    def use_mock(self) -> bool:
        # Mock is OPT-IN only (tests / offline dev). Real runs never silently fall back to
        # mock — a missing/invalid key surfaces a clear error instead of placeholder output.
        return self.llm_mode.strip().lower() == "mock"

    @property
    def has_api_key(self) -> bool:
        k = self.active_api_key.strip()
        if self.is_gemini:
            return bool(k)  # Gemini keys don't follow the sk-/PASTE_YOUR convention
        return bool(k) and "PASTE_YOUR" not in k and k.startswith("sk-")

    # ---- resolved paths ----
    def _abs(self, p: str | Path) -> Path:
        p = Path(p)
        return p if p.is_absolute() else _PROJECT_ROOT / p

    @property
    def runs_path(self) -> Path:
        return self._abs(self.runs_dir)

    @property
    def generated_tutorials_path(self) -> Path:
        # Default (empty setting) → top-level repo dir, i.e. the parent of the backend root.
        if self.generated_tutorials_dir:
            return self._abs(self.generated_tutorials_dir)
        return _PROJECT_ROOT.parent / "generated_tutorials"

    @property
    def templates_path(self) -> Path:
        return self._abs(self.templates_dir)

    @property
    def eval_sets_path(self) -> Path:
        return self._abs(self.eval_sets_dir)

    @property
    def package_prompts_path(self) -> Path:
        return _PACKAGE_DIR / "prompts"

    @property
    def package_skills_path(self) -> Path:
        return _PACKAGE_DIR / "skills"

    @property
    def reference_animations_path(self) -> Path:
        return _PROJECT_ROOT / "reference_animations"

    @property
    def mcq_prompt_file(self) -> Path:
        return self._abs(self.mcq_prompt_path)

    @property
    def block_division_prompt_file(self) -> Path:
        return self._abs(self.block_division_prompt_path)

    @property
    def db_url(self) -> str:
        return (self.supabase_db_url or "").strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
