from alembic import context
from sqlalchemy import create_engine, text

from app.config import settings
from app.models import Base

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    # PostGIS/tiger 등 확장이 만든 테이블은 무시
    return not (type_ == "table" and name in {"spatial_ref_sys"})


def run_migrations_online() -> None:
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
