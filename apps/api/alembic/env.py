import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from sqa.core.config import get_settings
from sqa.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    settings = get_settings()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # Read by migrations to grant least-privilege access to the app role.
        app_role=settings.db_app_role,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async() -> None:
    url = config.attributes.get("url") or get_settings().async_migrations_url
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline migrations are not supported.")
asyncio.run(run_async())
