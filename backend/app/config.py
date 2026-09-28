import os
import secrets

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# anchor to the repo layout so cwd never matters (WMI launch, deploy script, scripts/...)
_THIS = os.path.abspath(__file__)
_BACKEND_DIR = os.path.dirname(os.path.dirname(_THIS))       # backend/
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)                   # project root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(_BACKEND_DIR, ".env"),
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg2://cmpdi:cmpdi@localhost:5432/cmpdi"
    api_token: str = ""
    auth_secret: str = ""
    llm_base_url: str = "http://localhost:8001/v1"
    llm_api_key: str = "EMPTY"
    llm_model: str = "Qwen/Qwen2.5-7B-Instruct"
    # 384-dim to match chunks.embedding Vector(384); e5-base would be 768-dim and fail inserts
    embedding_model: str = "intfloat/multilingual-e5-small"
    data_dir: str = os.path.join(_REPO_ROOT, "data")
    repo_root: str = _REPO_ROOT
    chunk_size: int = 800
    chunk_overlap: int = 100
    ocr_lang: str = "eng+hin"
    confidence_threshold: float = 0.7
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_enabled: bool = True
    rate_limit_per_min: int = 120
    vector_enabled: bool = True
    admin_user: str = "admin"
    admin_password: str = ""
    # When True, queries for dates with no stored shift report synthesize a realistic
    # one (demo data generator). Keep OFF in anything resembling production - synthetic
    # statutory records must never be presented as real.
    demo_mode: bool = False

    @model_validator(mode="after")
    def _anchor_data_dir(self):
        # .env may carry a relative data_dir (e.g. ./data); resolve it against the repo
        # root so the value is independent of the process working directory
        if not os.path.isabs(self.data_dir):
            self.data_dir = os.path.normpath(os.path.join(_REPO_ROOT, self.data_dir))
        return self

    @model_validator(mode="after")
    def _ensure_auth_secret(self):
        if not self.auth_secret:
            self.auth_secret = secrets.token_urlsafe(32)
            print("[warn] AUTH_SECRET not set - using per-process random secret (tokens will not survive restarts)")
        return self


settings = Settings()
