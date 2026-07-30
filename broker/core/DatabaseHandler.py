from collections.abc import Iterable
from datetime import datetime
from uuid import UUID, uuid4

import aiosqlite
from contract.schemas.architecture import BrowsingRecord
from pydantic import HttpUrl

from broker.api.schemas.scrape import ScrapeRequest, ScrapeResponse
from broker.Config import Config
from broker.core.models.common import Event
from broker.core.models.DatabaseHandler import RecordTarget


class DatabaseHandler:
    __conn: aiosqlite.Connection = None

    @classmethod
    async def initialize(cls) -> None:

        cls.__conn = await aiosqlite.connect(Config.BROKER_DATABASE)
        cls.__conn.row_factory = aiosqlite.Row
        # await cls.__conn.execute("PRAGMA journal_mode=WAL;")
        # bug with this feature, extend the db infinitly
        await cls.__conn.commit()

        await cls.__initialize_database()

    @classmethod
    async def close(cls) -> None:
        if cls.__conn:
            await cls.__conn.close()
            cls.__conn = None

    @classmethod
    async def __initialize_database(cls) -> None:
        if Config.BROKER_CLEAR_DB_ON_STARTUP:
            await cls.__conn.execute(f"""
                DROP TABLE IF EXISTS {Config.DB_TABLE_TARGETS};
            """)
            await cls.__conn.execute(f"""
                DROP TABLE IF EXISTS {Config.DB_TABLE_JOBS};
            """)
            await cls.__conn.execute(f"""
                DROP TABLE IF EXISTS {Config.DB_TABLE_LOGS};
            """)

        await cls.__conn.execute(f"""
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

        await cls.__conn.execute(f"""
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

        await cls.__conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {Config.DB_TABLE_LOGS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                detail TEXT,
                level TEXT NOT NULL
            );
        """)

        await cls.__conn.commit()

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
        await cls.__conn.execute(query)
        await cls.__conn.commit()

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
        await cls.__conn.execute(query)
        await cls.__conn.commit()

    @classmethod
    async def disable_unassigned_targets(cls) -> None:
        """
        clear unassigned targets that have no reference in requests
        we cannot drop the rows as if a try has been make, there is a request record
        pointing to the target url (which we have to keep a reference to)
        """
        await cls.__conn.execute(f"""
            UPDATE {Config.DB_TABLE_TARGETS} AS l
            SET enabled = FALSE;
        """)
        await cls.__conn.commit()

    @classmethod
    async def get_top_target_excluding_running_ones(
        cls, uuids: Iterable[UUID]
    ) -> RecordTarget | None:
        current_tasks_ids_placeholder = "".join(
            [f"AND l.uuid != '{uuid}' " for uuid in uuids]
        )
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_TARGETS} l
            WHERE 1=1
                {current_tasks_ids_placeholder}
                AND l.enabled = 1
            ORDER BY l.expected_response_time ASC
        """
        cursor = await cls.__conn.execute(query)
        response = await cursor.fetchone()
        return RecordTarget.model_validate(dict(response)) if response else None

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
            LIMIT {Config.LIMIT_SQL_QUERIES};
        """
        cursor = await cls.__conn.execute(query)
        return [
            RecordTarget.model_validate(dict(record))
            for record in await cursor.fetchall()
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
            LIMIT {Config.LIMIT_SQL_QUERIES};
        """
        cursor = await cls.__conn.execute(query)
        return [
            RecordTarget.model_validate(dict(record))
            for record in await cursor.fetchall()
        ]

    @classmethod
    async def get_targets_from_uuids(cls, uuids: list[UUID]) -> list[RecordTarget]:
        placeholder = ",".join("?" for _ in uuids)
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_TARGETS}
            WHERE uuid in ({placeholder});
        """
        params = tuple(str(uuid) for uuid in uuids)
        cursor = await cls.__conn.execute(query, params)
        return [
            RecordTarget.model_validate(dict(record))
            for record in await cursor.fetchall()
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
        await cls.__conn.executemany(query, rows)
        await cls.__conn.commit()

    @classmethod
    async def insert_log(cls, event: Event) -> None:
        query = f"INSERT INTO {Config.DB_TABLE_LOGS} (timestamp, detail, level) VALUES (?, ?, ?)"
        row = (event.timestamp, event.detail, event.level)
        await cls.__conn.execute(query, row)
        await cls.__conn.commit()

    @classmethod
    async def insert_scrape_request(cls, request: ScrapeRequest) -> ScrapeResponse:
        uuids: list[UUID] = []
        query = f"""
            INSERT INTO {Config.DB_TABLE_TARGETS}
            (uuid, url, expected_response_time, tag, flag_lazy_loading)
            VALUES (?, ?, ?, ?, ?)
        """
        rows: list[tuple[str, str, datetime, str, bool]] = []
        urls = [request.url] if isinstance(request.url, HttpUrl) else request.url
        for url in urls:
            uuid = uuid4()
            uuids.append(uuid)
            rows.append(
                (
                    str(uuid),
                    str(url),
                    request.expected_response_time,
                    request.tag,
                    request.flag_lazy_loading,
                )
            )
        await cls.__conn.executemany(query, rows)
        await cls.__conn.commit()
        return ScrapeResponse(uuid=uuids if len(uuids) > 1 else uuids[0])
