from typing import Any
from uuid import UUID

import aiosqlite
from contract.schemas.architecture import BrowsingRecord

from broker.Config import Config
from broker.core.models.DatabaseHandler import RecordTarget


class DatabaseHandler:
    """
    the handlers should be dropped
    """

    __connection: aiosqlite.Connection = None

    @classmethod
    async def initialize(cls) -> None:

        cls.__connection = await aiosqlite.connect(Config.BROKER_DATABASE)
        cls.__connection.row_factory = aiosqlite.Row
        # await cls.__connection.execute("PRAGMA journal_mode=WAL;")
        # bug with this feature, extend the db infinitly
        await cls.__connection.commit()

        await cls.__initialize_database()

    @classmethod
    async def close(cls) -> None:

        if cls.__connection:
            await cls.__connection.close()
            cls.__connection = None

    @classmethod
    async def execute(cls, query: str, params: tuple[Any, ...] | None = None) -> None:
        """
        handlers not aiming for reuse (does not return a cursor)
        but here we only have just one type of fetch per query
        """
        await cls.__connection.execute(query, params)
        await cls.__connection.commit()

    @classmethod
    async def executemany(
        cls, query: str, params: tuple[Any, ...] | None = None
    ) -> None:
        await cls.__connection.executemany(query, params)
        await cls.__connection.commit()

    @classmethod
    async def fetchone(
        cls, query: str, params: tuple[Any, ...] | None = None
    ) -> dict[str, Any]:
        cursor = await cls.__connection.execute(query, params)
        return await cursor.fetchone()

    @classmethod
    async def fetchall(
        cls, query: str, params: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        cursor = await cls.__connection.execute(query, params)
        return await cursor.fetchall()

    @classmethod
    async def __initialize_database(cls) -> None:
        if Config.BROKER_CLEAR_DB_ON_STARTUP:
            await cls.__connection.execute(f"""
                DROP TABLE IF EXISTS {Config.DB_TABLE_TARGETS};
            """)
            await cls.__connection.execute(f"""
                DROP TABLE IF EXISTS {Config.DB_TABLE_JOBS};
            """)
            await cls.__connection.execute(f"""
                DROP TABLE IF EXISTS {Config.DB_TABLE_LOGS};
            """)

        await cls.__connection.execute(f"""
            CREATE TABLE IF NOT EXISTS {Config.DB_TABLE_TARGETS} (
                uuid TEXT PRIMARY KEY NOT NULL,
                url TEXT NOT NULL,
                expected_response_time DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                tag TEXT NOT NULL,
                flag_lazy_loading BOOLEAN NOT NULL,
                enabled BOOLEAN DEFAULT 1 NOT NULL
            );
        """)

        await cls.__connection.execute(f"""
            CREATE TABLE IF NOT EXISTS {Config.DB_TABLE_JOBS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {Config.DB_TABLE_TARGETS}_uuid TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                status TEXT NOT NULL,
                tab_state TEXT,
                html TEXT,
                timestamp DATETIME,
                timedelta_driver_get FLOAT,
                timedelta_smart_wait FLOAT,
                timedelta_search_cf_challenge FLOAT,
                timedelta_resolve_cf_challenge FLOAT,
                timedelta_check_cf_blocking_content FLOAT,
                timedelta_lazy_loading FLOAT,
                timedelta_get_content FLOAT,
                traceback TEXT,
                http_error_code INT,
                FOREIGN KEY ({Config.DB_TABLE_TARGETS}_uuid) REFERENCES {Config.DB_TABLE_TARGETS}(uuid)
            );
        """)

        await cls.__connection.execute(f"""
            CREATE TABLE IF NOT EXISTS {Config.DB_TABLE_LOGS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                detail TEXT,
                level TEXT NOT NULL
            );
        """)

        await cls.__connection.commit()

    @classmethod
    async def disable_successfull_targets(cls) -> None:
        query = f"""
            UPDATE {Config.DB_TABLE_TARGETS} AS l
            SET enabled = FALSE
            WHERE 1=1
                AND l.enabled = 1
                AND EXISTS (
                    SELECT 1
                    FROM {Config.DB_TABLE_JOBS} r
                    WHERE 1=1
                        AND r.{Config.DB_TABLE_TARGETS}_uuid = l.uuid
                        AND r.success = TRUE
                );
        """
        await cls.__connection.execute(query)
        await cls.__connection.commit()

    @classmethod
    async def disable_unsuccesfull_targets(cls) -> None:
        query = f"""
            UPDATE {Config.DB_TABLE_TARGETS} AS l
            SET enabled = FALSE
            WHERE 1=1
                AND l.enabled = 1
                AND (
                    SELECT COUNT(*)
                    FROM {Config.DB_TABLE_JOBS} r
                    WHERE 1=1
                        AND r.{Config.DB_TABLE_TARGETS}_uuid = l.uuid
                        AND r.success = FALSE
                ) >= {Config.RETRIES};
        """
        await cls.__connection.execute(query)
        await cls.__connection.commit()

    @classmethod
    async def disable_unassigned_targets(cls) -> None:
        """
        clear unassigned targets that have no reference in requests
        we cannot drop the rows as if a try has been make, there is a request record
        pointing to the target url (which we have to keep a reference to)
        """
        await cls.__connection.execute(f"""
            UPDATE {Config.DB_TABLE_TARGETS} AS l
            SET enabled = FALSE;
        """)
        await cls.__connection.commit()

    @classmethod
    async def get_unscraped_targets(cls) -> list[RecordTarget]:
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_TARGETS} l
            WHERE 1=1
                AND enabled = TRUE
                AND NOT EXISTS (
                    SELECT 1
                    FROM {Config.DB_TABLE_JOBS} r
                    WHERE 1=1
                        AND r.{Config.DB_TABLE_TARGETS}_uuid = l.uuid
                        AND r.success = TRUE
                )
            ORDER BY expected_response_time ASC
            LIMIT {Config.LIMIT_SQL_QUERIES}
        """
        return [
            RecordTarget.model_validate(dict(record))
            for record in await cls.fetchall(query)
        ]

    @classmethod
    async def get_scraped_targets(cls) -> list[RecordTarget]:
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_TARGETS} l
            WHERE EXISTS (
                SELECT 1
                FROM {Config.DB_TABLE_JOBS} r
                WHERE 1=1
                    AND r.{Config.DB_TABLE_TARGETS}_uuid = l.uuid
                    AND r.success = TRUE
                )
            ORDER BY expected_response_time ASC
            LIMIT {Config.LIMIT_SQL_QUERIES}
        """
        return [
            RecordTarget.model_validate(dict(record))
            for record in await cls.fetchall(query)
        ]

    @classmethod
    async def get_targets_from_uuids(cls, uuids: list[UUID]) -> list[RecordTarget]:
        placeholder = ",".join("?" for _ in uuids)
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_TARGETS}
            WHERE uuid in ({placeholder});
        """
        return [
            RecordTarget.model_validate(dict(record))
            for record in await cls.fetchall(
                query, params=tuple(str(uuid) for uuid in uuids)
            )
        ]

    @classmethod
    async def insert_job_records(cls, records: list[BrowsingRecord]):
        query = f"""
            INSERT INTO {Config.DB_TABLE_JOBS} (
                {Config.DB_TABLE_TARGETS}_uuid,
                success,
                status,
                tab_state,
                html,
                timestamp,
                timedelta_driver_get,
                timedelta_smart_wait,
                timedelta_search_cf_challenge,
                timedelta_resolve_cf_challenge,
                timedelta_check_cf_blocking_content,
                timedelta_lazy_loading,
                timedelta_get_content,
                traceback,
                http_error_code
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                str(record.target_uuid),
                record.success,
                record.status,
                record.tab_state,
                record.html,
                record.timestamp,
                record.timedelta_driver_get,
                record.timedelta_smart_wait,
                record.timedelta_search_cf_challenge,
                record.timedelta_resolve_cf_challenge,
                record.timedelta_check_cf_blocking_content,
                record.timedelta_lazy_loading,
                record.timedelta_get_content,
                record.traceback,
                record.http_error_code,
            )
            for record in records
        ]
        await cls.__connection.executemany(query, rows)
        await cls.__connection.commit()
