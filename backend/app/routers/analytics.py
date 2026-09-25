import datetime

from fastapi import APIRouter, Depends

from ..auth import require_min_role, scoped_subsidiary
from ..services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _parse_date(value: str | None) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


@router.get("/wordcloud")
def wordcloud(
    subsidiary: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    top_n: int = 60,
    user=Depends(require_min_role("viewer")),
):
    return analytics.wordcloud(scoped_subsidiary(user, subsidiary), year_from, year_to, top_n)


@router.get("/topics")
def topics(
    subsidiary: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    top_n: int = 15,
    user=Depends(require_min_role("viewer")),
):
    return analytics.topics(scoped_subsidiary(user, subsidiary), year_from, year_to, top_n)


@router.get("/trends")
def trends(field_name: str, subsidiary: str = "", user=Depends(require_min_role("viewer"))):
    return analytics.trends(field_name, scoped_subsidiary(user, subsidiary))


@router.get("/topic_trends")
def topic_trends(
    subsidiary: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    per_year: int = 5,
    user=Depends(require_min_role("viewer")),
):
    return analytics.topic_trends(scoped_subsidiary(user, subsidiary), year_from, year_to, per_year)


@router.get("/stoppage_pareto")
def stoppage_pareto(
    subsidiary: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
    top_n: int = 15,
    user=Depends(require_min_role("viewer")),
):
    """Downtime by stoppage-reason category (Pareto), per-machine totals, top raw reasons."""
    return analytics.stoppage_pareto(
        scoped_subsidiary(user, subsidiary), _parse_date(date_from), _parse_date(date_to), top_n
    )


@router.get("/kpis")
def kpis(user=Depends(require_min_role("viewer"))):
    """PS headline metrics: automation %, extraction accuracy %, report prep-time reduction."""
    return analytics.kpis()


@router.get("/machine_utilization")
def machine_utilization(
    subsidiary: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    user=Depends(require_min_role("viewer")),
):
    """Per-machine EWH/TWH utilization % and output, aggregated over the period."""
    return analytics.machine_utilization(
        scoped_subsidiary(user, subsidiary), _parse_date(date_from), _parse_date(date_to), limit
    )
