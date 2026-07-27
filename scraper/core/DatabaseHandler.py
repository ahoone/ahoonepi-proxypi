import os
from uuid import UUID

import aiosqlite

from scraper.Config import Config
from scraper.core.models.DatabaseHandler import ProfileNotFoundError, RecordProfile


class DatabaseHandler:
    __conn: aiosqlite.Connection = None

    @classmethod
    async def initialize(cls) -> None:
        os.makedirs("/app/data", exist_ok=True)
        cls.__conn = await aiosqlite.connect(Config.SCRAPER_DATABASE)
        cls.__conn.row_factory = aiosqlite.Row
        await cls.__conn.commit()

        await cls.__initialize_database()

    @classmethod
    async def __initialize_database(cls) -> None:
        await cls.__conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {Config.DB_TABLE_PROFILES} (
                profile_uuid TEXT PRIMARY KEY NOT NULL,
                profile_name TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """)

    @classmethod
    async def get_profile_from_uuid(cls, profile_uuid: UUID) -> RecordProfile:
        """
        Summary.

        Args:
            profile_uuid (UUID): Description.

        Returns:
            RecordProfile: Description.

        Raises:
            ValueError: If the target `UUID` is not found.
        """
        query = f"""
            SELECT *
            FROM {Config.DB_TABLE_PROFILES}
            WHERE profile_uuid = ?;
        """
        row = await cls.__conn.fetchone(query, params=(str(profile_uuid),))
        if not row:
            raise ProfileNotFoundError(f"No record of profile {profile_uuid} found.")
        return RecordProfile.model_validate(dict(row))

    @classmethod
    async def insert_record_profile(cls, record_profile: RecordProfile):
        query = f"""
            INSERT INTO {Config.DB_TABLE_PROFILES} (
                profile_uuid,
                profile_name,
                created_at
            )
            VALUES (?, ?, ?);
        """
        row = (
            record_profile.profile_uuid,
            record_profile.profile_name,
            record_profile.created_at,
        )
        await cls.__conn.execute(query, row)
        await cls.__conn.commit()
