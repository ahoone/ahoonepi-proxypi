from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import aiosqlite
from Config import Config
from core.models.DatabaseHandler import RecordTarget


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

        await cls.initialize_database()

    @classmethod
    async def close(cls) -> None:

        if cls.__connection:
            await cls.__connection.close()
            cls.__connection = None

    @classmethod
    async def execute(
        cls, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> None:
        """
        handlers not aiming for reuse (does not return a cursor)
        but here we only have just one type of fetch per query
        """
        await cls.__connection.execute(query, params)
        await cls.__connection.commit()

    @classmethod
    async def executemany(
        cls, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> None:
        await cls.__connection.executemany(query, params)
        await cls.__connection.commit()

    @classmethod
    async def fetchone(
        cls, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> Dict[str, Any]:
        cursor = await cls.__connection.execute(query, params)
        return await cursor.fetchone()

    @classmethod
    async def fetchall(
        cls, query: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        cursor = await cls.__connection.execute(query, params)
        return await cursor.fetchall()

    @classmethod
    async def initialize_database(cls) -> None:
        if Config.BROKER_CLEAR_DB_ON_STARTUP:
            await cls.__connection.execute(f"""
                DROP TABLE IF EXISTS {Config.DB_TABLE_TARGETS};
            """)
            await cls.__connection.execute(f"""
                DROP TABLE IF EXISTS {Config.DB_TABLE_REQUESTS};
            """)
            await cls.__connection.execute(f"""
                DROP TABLE IF EXISTS {Config.DB_TABLE_LOGS};
            """)

        await cls.__connection.execute(f"""
            CREATE TABLE IF NOT EXISTS {Config.DB_TABLE_TARGETS} (
                id TEXT PRIMARY KEY NOT NULL,
                url TEXT NOT NULL,
                antwortzeit DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                tag TEXT NOT NULL,
                flag_lazy_loading BOOLEAN NOT NULL,
                enabled BOOLEAN DEFAULT 1 NOT NULL
            );
        """)

        await cls.__connection.execute(f"""
            CREATE TABLE IF NOT EXISTS {Config.DB_TABLE_REQUESTS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {Config.DB_TABLE_TARGETS}_id TEXT NOT NULL,
                request_timestamp DATETIME NOT NULL,
                response_timestamp DATETIME,
                success BOOLEAN,
                content BLOB,
                FOREIGN KEY ({Config.DB_TABLE_TARGETS}_id) REFERENCES {Config.DB_TABLE_TARGETS}(id)
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
                    FROM {Config.DB_TABLE_REQUESTS} r
                    WHERE 1=1
                        AND r.{Config.DB_TABLE_TARGETS}_id = l.id
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
                    FROM {Config.DB_TABLE_REQUESTS} r
                    WHERE 1=1
                        AND r.{Config.DB_TABLE_TARGETS}_id = l.id
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
    async def get_unscraped_targets(cls) -> List[RecordTarget]:
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_TARGETS} l
            WHERE 1=1
                AND enabled = TRUE
                AND NOT EXISTS (
                    SELECT 1
                    FROM {Config.DB_TABLE_REQUESTS} r
                    WHERE 1=1
                        AND r.{Config.DB_TABLE_TARGETS}_id = l.id
                        AND r.success = TRUE
                )
            ORDER BY antwortzeit ASC
            LIMIT {Config.LIMIT_SQL_QUERIES}
        """
        return [
            RecordTarget(
                id=record["id"],
                url=record["url"],
                antwortzeit=record["antwortzeit"],
                created_at=record["created_at"],
                tag=record["tag"],
                flag_lazy_loading=record["flag_lazy_loading"],
            )
            for record in await cls.fetchall(query)
        ]

    @classmethod
    async def get_scraped_targets(cls) -> List[Dict[str, Any]]:
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_REQUESTS}
            WHERE success = TRUE
            ORDER BY id ASC
            LIMIT {Config.LIMIT_SQL_QUERIES}
        """
        return await cls.fetchall(query)

    @classmethod
    async def get_targets_from_uuids(cls, uuids: List[UUID]) -> List[RecordTarget]:
        placeholder = ",".join("?" for _ in uuids)
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_TARGETS}
            WHERE id in ({placeholder});
        """
        return [
            RecordTarget(
                id=record["id"],
                url=record["url"],
                antwortzeit=record["antwortzeit"],
                created_at=record["created_at"],
                tag=record["tag"],
                flag_lazy_loading=record["flag_lazy_loading"],
            )
            for record in await cls.fetchall(
                query, params=tuple(str(uuid) for uuid in uuids)
            )
        ]
