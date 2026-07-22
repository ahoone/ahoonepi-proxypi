import aiosqlite

from scraper.Config import Config


class DatabaseHandler:
    __conn: aiosqlite.Connection = None

    @classmethod
    async def initialize(cls) -> None:
        cls.__conn = await aiosqlite.connect(Config.SCRAPER_DATABASE)
        cls.__conn.row_factory = aiosqlite.Row
        await cls.__conn.commit()

        await cls.__initialize_database()

    @classmethod
    async def __initialize_database(cls) -> None:
        await cls.__conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {Config.DB_TABLE_PROFILES}
        """)
