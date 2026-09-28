
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

_engine = None
_session_factory = None


class Base(DeclarativeBase):
    pass


def get_engine():
    global _engine
    if _engine is None:
        # lazy so imports never load the DB driver (DLL may be blocked on locked-down Windows)
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def SessionLocal():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate():
    """Lightweight column migrations for tables created by older versions."""
    if get_engine().dialect.name != "postgresql":
        return
    with get_engine().connect() as conn:
        cols = [
            r[0]
            for r in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'extraction_fields'")
            )
        ]
        if cols and "subsidiary" not in cols:
            conn.execute(text("ALTER TABLE extraction_fields ADD COLUMN subsidiary VARCHAR(100) DEFAULT ''"))
            conn.commit()
            print("[migrate] added extraction_fields.subsidiary")
        jcols = [
            r[0]
            for r in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'jobs'")
            )
        ]
        if jcols and "updated_at" not in jcols:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN updated_at TIMESTAMPTZ"))
            conn.commit()
            print("[migrate] added jobs.updated_at")
        dcols = [
            r[0]
            for r in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'documents'")
            )
        ]
        if dcols and "doc_date" not in dcols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN doc_date DATE"))
            conn.commit()
            print("[migrate] added documents.doc_date")
        if dcols and "approved_by" not in dcols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN approved_by VARCHAR(200) DEFAULT ''"))
            conn.commit()
            print("[migrate] added documents.approved_by")
        if dcols and "approved_at" not in dcols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN approved_at TIMESTAMPTZ"))
            conn.commit()
            print("[migrate] added documents.approved_at")
        if dcols and "specified_by" not in dcols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN specified_by VARCHAR(200) DEFAULT ''"))
            conn.commit()
            print("[migrate] added documents.specified_by")
        fcols = [
            r[0]
            for r in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'extraction_fields'")
            )
        ]
        if fcols and "item" not in fcols:
            conn.execute(text("ALTER TABLE extraction_fields ADD COLUMN item VARCHAR(200) DEFAULT ''"))
            conn.commit()
            print("[migrate] added extraction_fields.item")
        if fcols and "approved_by" not in fcols:
            conn.execute(text("ALTER TABLE extraction_fields ADD COLUMN approved_by VARCHAR(200) DEFAULT ''"))
            conn.commit()
            print("[migrate] added extraction_fields.approved_by")
        if fcols and "specified_by" not in fcols:
            conn.execute(text("ALTER TABLE extraction_fields ADD COLUMN specified_by VARCHAR(200) DEFAULT ''"))
            conn.commit()
            print("[migrate] added extraction_fields.specified_by")
        qlcols = [
            r[0]
            for r in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'query_log'")
            )
        ]
        if qlcols and "rating" not in qlcols:
            conn.execute(text("ALTER TABLE query_log ADD COLUMN rating INTEGER"))
            conn.commit()
            print("[migrate] added query_log.rating")
        if qlcols and "feedback_text" not in qlcols:
            conn.execute(text("ALTER TABLE query_log ADD COLUMN feedback_text TEXT"))
            conn.commit()
            print("[migrate] added query_log.feedback_text")
        jcols2 = [
            r[0]
            for r in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'jobs'")
            )
        ]
        if jcols2 and "priority" not in jcols2:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 0"))
            conn.commit()
            print("[migrate] added jobs.priority")


def init_db():
    if settings.vector_enabled:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
        except Exception as e:
            print(f"[warn] pgvector extension unavailable - vector search disabled ({e.__class__.__name__})")
    from . import models  # noqa: F401  (registers tables on Base)

    Base.metadata.create_all(get_engine())
    _migrate()
