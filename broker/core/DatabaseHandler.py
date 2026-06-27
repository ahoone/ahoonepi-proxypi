from typing import Any, Dict, List, Optional, Tuple

import aiosqlite
from Config import Config


class DatabaseHandler:
    __connection: aiosqlite.Connection = None

    @classmethod
    async def initialize(cls) -> None:

        cls.__connection = await aiosqlite.connect(Config.BROKER_DATABASE)
        cls.__connection.row_factory = aiosqlite.Row
        await cls.__connection.execute("PRAGMA journal_mode=WAL;")
        await cls.__connection.commit()

        await cls.initialize_database()

    @classmethod
    async def close(cls) -> None:

        if cls.__connection:
            await cls.__connection.close()
            cls.__connection = None

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
                tag TEXT NOT NULL
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
    async def execute(cls, query: str, params: Optional[Tuple[Any]] = None) -> None:
        """
        handlers not aiming for reuse (does not return a cursor)
        but here we only have just one type of fetch per query
        """
        await cls.__connection.execute(query, params)
        await cls.__connection.commit()

    @classmethod
    async def executemany(cls, query: str, params: Optional[Tuple[Any]] = None) -> None:
        await cls.__connection.executemany(query, params)
        await cls.__connection.commit()

    @classmethod
    async def fetchone(
        cls, query: str, params: Optional[Tuple[Any]] = None
    ) -> Dict[str, Any]:
        cursor = await cls.__connection.execute(query, params)
        return await cursor.fetchone()

    @classmethod
    async def fetchall(
        cls, query: str, params: Optional[Tuple[Any]] = None
    ) -> List[Dict[str, Any]]:
        cursor = await cls.__connection.execute(query, params)
        return await cursor.fetchall()
