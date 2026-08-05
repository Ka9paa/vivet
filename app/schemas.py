from pydantic import BaseModel, Field


class InitRequest(BaseModel):
    app_id: str
    app_secret: str


class LicenseAuthRequest(BaseModel):
    app_id: str
    session_id: str
    license_key: str = Field(min_length=3, max_length=100)
    hwid: str = Field(min_length=3, max_length=255)


class AppCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class LicenseCreateRequest(BaseModel):
    duration_days: int | None = Field(default=30, ge=1, le=3650)
    note: str | None = Field(default=None, max_length=255)
