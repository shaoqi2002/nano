from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def create_tables() -> None:
    import app.model  # noqa: F401

    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)
        # Stable built-in workspace. Existing records are assigned to it before
        # workspace columns become mandatory.
        await connection.execute(text("""
            INSERT INTO workspaces (id, name, slug)
            VALUES ('00000000-0000-0000-0000-0000000000c4', 'ch4', 'ch4')
            ON CONFLICT (id) DO NOTHING
        """))
        for table_name in (
            "conversations",
            "documents",
            "job_applications",
            "agent_eval_runs",
            "agent_eval_cases",
        ):
            await connection.execute(text(f"""
                ALTER TABLE {table_name}
                ADD COLUMN IF NOT EXISTS workspace_id UUID
            """))
            await connection.execute(text(f"""
                UPDATE {table_name}
                SET workspace_id = '00000000-0000-0000-0000-0000000000c4'
                WHERE workspace_id IS NULL
            """))
            await connection.execute(text(f"""
                ALTER TABLE {table_name}
                ALTER COLUMN workspace_id SET NOT NULL
            """))
            await connection.execute(text(f"""
                CREATE INDEX IF NOT EXISTS ix_{table_name}_workspace_id
                ON {table_name} (workspace_id)
            """))
            await connection.execute(text(f"""
                DO $$ BEGIN
                    ALTER TABLE {table_name}
                    ADD CONSTRAINT fk_{table_name}_workspace_id
                    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$
            """))
        # create_all does not alter installations that already contain these tables.
        await connection.execute(text("""
            ALTER TABLE documents
            ADD COLUMN IF NOT EXISTS index_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS index_error TEXT,
            ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS parser_version VARCHAR(20),
            ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(100)
        """))
        await connection.execute(text("""
            ALTER TABLE messages
            ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS options JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS artifacts JSONB NOT NULL DEFAULT '[]'::jsonb
        """))
        await connection.execute(text("""
            ALTER TABLE agent_runs
            ADD COLUMN IF NOT EXISTS duration_ms INTEGER,
            ADD COLUMN IF NOT EXISTS tool_call_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS tool_failure_count INTEGER NOT NULL DEFAULT 0
        """))


async def close_database() -> None:
    await engine.dispose()
