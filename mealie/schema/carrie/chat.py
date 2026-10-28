from datetime import date
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from mealie.schema._mealie import MealieModel


class CarrieContext(MealieModel):
    start_date: date
    end_date: date
    diner_ids: list[UUID] = Field(default_factory=list, max_length=50)
    include_cooking: bool = True

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if not 0 <= (self.end_date - self.start_date).days <= 62:
            raise ValueError("Choose a date range of at most 63 days")
        return self


class CarrieSend(CarrieContext):
    message: str = Field(min_length=1, max_length=8000)
    request_id: UUID
    expected_leaf_entry_id: str | None = Field(default=None, max_length=256)


class CarrieStatus(MealieModel):
    enabled: bool
    stock_path: str | None = None
    stock_agent_id: str | None = None


class CarrieMessage(MealieModel):
    id: str
    role: Literal["user", "assistant"]
    text: str


class CarrieHistory(MealieModel):
    messages: list[CarrieMessage]
    running: bool = False
    leaf_entry_id: str | None = None
    truncated: bool = False


class CarrieAccepted(MealieModel):
    run_id: str
