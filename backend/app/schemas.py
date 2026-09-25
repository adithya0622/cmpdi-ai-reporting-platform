from pydantic import BaseModel


class GenerateIn(BaseModel):
    title: str
    subsidiary: str = ""
    year_from: int | None = None
    year_to: int | None = None


class QueryIn(BaseModel):
    question: str
    subsidiary: str = ""
    top_k: int = 8
    history: list[dict] = []
