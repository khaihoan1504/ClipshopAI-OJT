
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.storage import resolve_media_url


class ProductImageCreate(BaseModel):
    product_id: int
    object_key: str
    is_primary: bool = False
    sort_order: int = 0


class ProductImageUpdate(BaseModel):
    object_key: str | None = None
    is_primary: bool | None = None
    sort_order: int | None = None


class ProductImageOut(BaseModel):
    id: int
    product_id: int
    object_key: str
    is_primary: bool
    sort_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("object_key", mode="after")
    @classmethod
    def _resolve_object_key(cls, value: str) -> str:
        return resolve_media_url(value) or value
