"""Application configuration.

All paths are resolved relative to the project root (the directory containing
`pyproject.toml`) unless overridden via environment variables (see .env.example).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SAX2SHEET_", env_file=".env")

    data_dir: Path = REPO_ROOT / "data"
    max_upload_mb: int = 100

    # Basic Pitch defaults — exposed to the API so the frontend can override
    # per-transcription without touching the model.
    onset_threshold: float = 0.5
    frame_threshold: float = 0.3
    minimum_note_length_ms: float = 58.0
    minimum_frequency_hz: float = 80.0   # below written low Bb3 with margin
    maximum_frequency_hz: float = 2000.0  # above written high F#6 with margin

    @property
    def projects_dir(self) -> Path:
        d = self.data_dir / "projects"
        d.mkdir(parents=True, exist_ok=True)
        return d


settings = Settings()
