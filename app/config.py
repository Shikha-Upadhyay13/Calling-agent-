from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    user_phone_number: str

    deepgram_api_key: str
    groq_api_key: str

    public_base_url: str


settings = Settings()
