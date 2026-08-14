from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file="config.env",
        env_file_encoding="utf-8",
    )


config = Config()
