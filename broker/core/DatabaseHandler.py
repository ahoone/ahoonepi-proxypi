from typing import Any, Dict, List, Tuple

import aiosqlite
from Config import Config


class DatabaseHandler:
    @classmethod
    async def initialize(cls) -> None:

        async with aiosqlite.connect(Config.BROKER_DATABASE) as conn:
            if Config.BROKER_CLEAR_DB_ON_STARTUP:
                await DatabaseHandler.execute(f"""
                    DROP TABLE IF EXISTS {Config.DB_TABLE_TARGETS};
                """)
                await DatabaseHandler.execute(f"""
                    DROP TABLE IF EXISTS {Config.DB_TABLE_REQUESTS};
                """)

            response = await conn.execute("SELECT name FROM sqlite_master")
            if not response:
                return
            existing_tables = await response.fetchall()

            if Config.DB_TABLE_TARGETS not in existing_tables:
                await DatabaseHandler.execute(f"""
                    CREATE TABLE IF NOT EXISTS {Config.DB_TABLE_TARGETS} (
                        id TEXT PRIMARY KEY NOT NULL,
                        url TEXT NOT NULL,
                        antwortzeit DATETIME NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        tag TEXT NOT NULL
                    );
                """)

            if Config.DB_TABLE_REQUESTS not in existing_tables:
                await DatabaseHandler.execute(f"""
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

            # await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.commit()

    @classmethod
    async def execute(cls, query: str, params: Tuple[Any] = None) -> None:
        """
        handlers not aiming for reuse (does not return a cursor)
        but here we only have just one type of fetch per query
        """
        async with aiosqlite.connect(Config.BROKER_DATABASE) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute(query, params)
            await conn.commit()

    @classmethod
    async def executemany(cls, query: str, params: Tuple[Any] = None) -> None:
        async with aiosqlite.connect(Config.BROKER_DATABASE) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.executemany(query, params)
            await conn.commit()

    @classmethod
    async def fetchone(cls, query: str, params: Tuple[Any] = None) -> Dict[str, Any]:
        async with aiosqlite.connect(Config.BROKER_DATABASE) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, params)
            return await cursor.fetchone()

    @classmethod
    async def fetchall(
        cls, query: str, params: Tuple[Any] = None
    ) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(Config.BROKER_DATABASE) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, params)
            return await cursor.fetchall()
