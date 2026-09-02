import os
from uuid import UUID

import aiosqlite

from scraper.config import config
from scraper.core.models.DatabaseHandler import ProfileNotFoundError, ProfileRecord


class DatabaseHandler:
    __conn: aiosqlite.Connection = None

    @classmethod
    async def initialize(cls) -> None:
        os.makedirs("/app/data", exist_ok=True)
        cls.__conn = await aiosqlite.connect(config.SCRAPER_DATABASE)
        cls.__conn.row_factory = aiosqlite.Row
        await cls.__conn.commit()

        await cls.__initialize_database()

    @classmethod
    async def __initialize_database(cls) -> None:
        await cls.__conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {config.DB_TABLE_PROFILES} (
                profile_uuid TEXT PRIMARY KEY NOT NULL,
                profile_name TEXT NOT NULL,
                user_data_dir TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """)

    @classmethod
    async def get_profile_from_uuid(cls, profile_uuid: UUID) -> ProfileRecord:
        """
        Summary.

        Args:
            profile_uuid (UUID): Description.

        Returns:
            ProfileRecord: Description.

        Raises:
            ValueError: If the target `UUID` is not found.
        """
        query = f"""
            SELECT *
            FROM {config.DB_TABLE_PROFILES}
            WHERE profile_uuid = ?;
        """
        cursor = await cls.__conn.execute(query)
        row = await cursor.fetchone(query, params=(str(profile_uuid),))
        if not row:
            raise ProfileNotFoundError(f"No record of profile {profile_uuid} found.")
        return ProfileRecord.model_validate(dict(row))

    @classmethod
    async def insert_profile_record(cls, profile_record: ProfileRecord) -> None:
        query = f"""
            INSERT INTO {config.DB_TABLE_PROFILES} (
                profile_uuid,
                profile_name,
                user_data_dir,
                created_at
            )
            VALUES (?, ?, ?, ?);
        """
        row = (
            str(profile_record.uuid),
            profile_record.name,
            str(profile_record.user_data_dir),
            profile_record.created_at,
        )
        await cls.__conn.execute(query, row)
        await cls.__conn.commit()
