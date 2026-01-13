from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast
from urllib.parse import urljoin

from boto3.session import Session
from advanced_alchemy.utils.text import slugify
from litestar.data_extractors import RequestExtractorField
from litestar.serialization import decode_json, encode_json
from litestar.utils.module_loader import module_to_os_path
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from dataclasses import dataclass, field
import os
from pathlib import Path


from ._utils import get_env


if TYPE_CHECKING:
    from collections.abc import Callable

    from litestar.data_extractors import ResponseExtractorField

DEFAULT_MODULE_NAME = 'app'
BASE_DIR: Final[Path] = module_to_os_path(DEFAULT_MODULE_NAME)


@dataclass
class DatabaseSettings:
    ECHO: bool = field(default_factory=get_env('DATABASE_ECHO', False))
    """Enable SQLAlchemy engine logs."""
    ECHO_POOL: bool = field(default_factory=get_env('DATABASE_ECHO_POOL', False))
    """Enable SQLAlchemy connection pool logs."""
    POOL_DISABLED: bool = field(
        default_factory=get_env('DATABASE_POOL_DISABLED', False)
    )
    """Disable SQLAlchemy pool configuration."""
    POOL_MAX_OVERFLOW: int = field(
        default_factory=get_env('DATABASE_MAX_POOL_OVERFLOW', 10)
    )
    """Max overflow for SQLAlchemy connection pool"""
    POOL_SIZE: int = field(default_factory=get_env('DATABASE_POOL_SIZE', 5))
    """Pool size for SQLAlchemy connection pool"""
    POOL_TIMEOUT: int = field(default_factory=get_env('DATABASE_POOL_TIMEOUT', 30))
    """Time in seconds for timing connections out of the connection pool."""
    POOL_RECYCLE: int = field(default_factory=get_env('DATABASE_POOL_RECYCLE', 300))
    """Amount of time to wait before recycling connections."""
    POOL_PRE_PING: bool = field(
        default_factory=get_env('DATABASE_PRE_POOL_PING', False)
    )
    """Optionally ping database before fetching a session from the connection pool."""
    URL: str = field(
        default_factory=get_env('DATABASE_URL', 'sqlite+aiosqlite:///db.sqlite3')
    )
    """SQLAlchemy Database URL."""
    MIGRATION_CONFIG: str = field(
        default_factory=get_env(
            'DATABASE_MIGRATION_CONFIG', f'{BASE_DIR}/db/migrations/alembic.ini'
        )
    )
    """The path to the `alembic.ini` configuration file."""
    MIGRATION_PATH: str = field(
        default_factory=get_env('DATABASE_MIGRATION_PATH', f'{BASE_DIR}/db/migrations')
    )
    """The path to the `alembic` database migrations."""
    MIGRATION_DDL_VERSION_TABLE: str = field(
        default_factory=get_env('DATABASE_MIGRATION_DDL_VERSION_TABLE', 'ddl_version')
    )
    """The name to use for the `alembic` versions table name."""
    FIXTURE_PATH: str = field(
        default_factory=get_env('DATABASE_FIXTURE_PATH', f'{BASE_DIR}/db/fixtures')
    )
    """The path to JSON fixture files to load into tables."""
    _engine_instance: AsyncEngine | None = None
    """SQLAlchemy engine instance generated from settings."""

    @property
    def engine(self) -> AsyncEngine:
        return self.get_engine()

    def get_engine(self) -> AsyncEngine:
        if self._engine_instance is not None:
            return self._engine_instance
        if self.URL.startswith('postgresql+asyncpg'):
            engine = create_async_engine(
                url=self.URL,
                future=True,
                json_serializer=encode_json,
                json_deserializer=decode_json,
                echo=self.ECHO,
                echo_pool=self.ECHO_POOL,
                max_overflow=self.POOL_MAX_OVERFLOW,
                pool_size=self.POOL_SIZE,
                pool_timeout=self.POOL_TIMEOUT,
                pool_recycle=self.POOL_RECYCLE,
                pool_pre_ping=self.POOL_PRE_PING,
                pool_use_lifo=True,  # use lifo to reduce the number of idle connections
                poolclass=NullPool if self.POOL_DISABLED else None,
            )
            """Database session factory.

            See [`async_sessionmaker()`][sqlalchemy.ext.asyncio.async_sessionmaker].
            """

            @event.listens_for(engine.sync_engine, 'connect')
            def _sqla_on_connect(
                dbapi_connection: Any, _: Any
            ) -> Any:  # pragma: no cover
                """Using msgspec for serialization of the json column values means that the
                output is binary, not `str` like `json.dumps` would output.
                SQLAlchemy expects that the json serializer returns `str` and calls `.encode()` on the value to
                turn it to bytes before writing to the JSONB column. I'd need to either wrap `serialization.to_json` to
                return a `str` so that SQLAlchemy could then convert it to binary, or do the following, which
                changes the behaviour of the dialect to expect a binary value from the serializer.
                See Also https://github.com/sqlalchemy/sqlalchemy/blob/14bfbadfdf9260a1c40f63b31641b27fe9de12a0/lib/sqlalchemy/dialects/postgresql/asyncpg.py#L934  pylint: disable=line-too-long
                """

                def encoder(bin_value: bytes) -> bytes:
                    return b'\x01' + encode_json(bin_value)

                def decoder(bin_value: bytes) -> Any:
                    # the byte is the \x01 prefix for jsonb used by PostgreSQL.
                    # asyncpg returns it when format='binary'
                    return decode_json(bin_value[1:])

                dbapi_connection.await_(
                    dbapi_connection.driver_connection.set_type_codec(
                        'jsonb',
                        encoder=encoder,
                        decoder=decoder,
                        schema='pg_catalog',
                        format='binary',
                    ),
                )
                dbapi_connection.await_(
                    dbapi_connection.driver_connection.set_type_codec(
                        'json',
                        encoder=encoder,
                        decoder=decoder,
                        schema='pg_catalog',
                        format='binary',
                    ),
                )
        elif self.URL.startswith('sqlite+aiosqlite'):
            engine = create_async_engine(
                url=self.URL,
                future=True,
                json_serializer=encode_json,
                json_deserializer=decode_json,
                echo=self.ECHO,
                echo_pool=self.ECHO_POOL,
                pool_recycle=self.POOL_RECYCLE,
                pool_pre_ping=self.POOL_PRE_PING,
            )
            """Database session factory.

            See [`async_sessionmaker()`][sqlalchemy.ext.asyncio.async_sessionmaker].
            """

            @event.listens_for(engine.sync_engine, 'connect')
            def _sqla_on_connect(
                dbapi_connection: Any, _: Any
            ) -> Any:  # pragma: no cover
                """Override the default begin statement.  The disables the built in begin execution."""
                dbapi_connection.isolation_level = None

            @event.listens_for(engine.sync_engine, 'begin')
            def _sqla_on_begin(dbapi_connection: Any) -> Any:  # pragma: no cover
                """Emits a custom begin"""
                dbapi_connection.exec_driver_sql('BEGIN')
        else:
            engine = create_async_engine(
                url=self.URL,
                future=True,
                json_serializer=encode_json,
                json_deserializer=decode_json,
                echo=self.ECHO,
                echo_pool=self.ECHO_POOL,
                max_overflow=self.POOL_MAX_OVERFLOW,
                pool_size=self.POOL_SIZE,
                pool_timeout=self.POOL_TIMEOUT,
                pool_recycle=self.POOL_RECYCLE,
                pool_pre_ping=self.POOL_PRE_PING,
                pool_use_lifo=True,  # use lifo to reduce the number of idle connections
                poolclass=NullPool if self.POOL_DISABLED else None,
            )
        self._engine_instance = engine
        return self._engine_instance


@dataclass
class S3Settings:
    AWS_ACCESS_KEY_ID: str = field(default_factory=get_env('AWS_ACCESS_KEY_ID', ''))
    """The public key id."""
    AWS_SECRET_ACCESS_KEY: str = field(
        default_factory=get_env('AWS_SECRET_ACCESS_KEY', '')
    )
    """The secret key."""
    AWS_DEFAULT_REGION: str = field(default_factory=get_env('AWS_DEFAULT_REGION', ''))
    """Region name, e.g. eu-west-1"""
    S3_ENDPOINT_URL: str = field(default_factory=get_env('S3_ENDPOINT_URL', ''))
    """Endpoint URL including region."""
    S3_BUCKET_NAME: str = field(default_factory=get_env('S3_BUCKET_NAME', ''))
    """The bucket name."""

    def get_client(self) -> Any:
        session = Session()
        s3_client = session.client(
            service_name='s3',
            aws_access_key_id=self.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY,
            endpoint_url=self.S3_ENDPOINT_URL,
            region_name=self.AWS_DEFAULT_REGION,
        )
        return s3_client

    def get_bucket_url(self):
        return urljoin(self.S3_ENDPOINT_URL, self.S3_BUCKET_NAME)


@dataclass
class Settings:
    db: DatabaseSettings = field(default_factory=DatabaseSettings)
    s3: S3Settings = field(default_factory=S3Settings)

    @classmethod
    def from_env(cls, dotenv_filename: str = '.env') -> Settings:
        env_file = Path(f'{os.curdir}/{dotenv_filename}')
        if env_file.is_file():
            from dotenv import load_dotenv

            print(
                f'[yellow]Loading environment configuration from {dotenv_filename}[/]'
            )

            load_dotenv(env_file, override=True)
        return Settings()
