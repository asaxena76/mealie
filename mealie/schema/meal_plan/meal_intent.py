from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import UUID4, ConfigDict, Field, StringConstraints, field_validator, model_validator
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.household import MealPlanPreparation
from mealie.schema._mealie import MealieModel
from mealie.schema.response.pagination import PaginationBase


class DinerSelectionMode(StrEnum):
    all = "all"
    selected = "selected"


class DinerBase(MealieModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    abbreviation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4)]
    emoji: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=16)] = None
    color: str | None = None
    position: int = 0
    active: bool = True

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        invalid_character = any(character not in "0123456789abcdefABCDEF" for character in value[1:])
        if len(value) != 7 or value[0] != "#" or invalid_character:
            raise ValueError("color must be a hexadecimal value such as #E58325")
        return value.upper()


class CreateDiner(DinerBase): ...


class SaveDiner(DinerBase):
    group_id: UUID4
    household_id: UUID4


class UpdateDiner(DinerBase):
    id: UUID4


class DinerSummary(MealieModel):
    id: UUID4
    name: str
    abbreviation: str
    emoji: str | None = None
    color: str | None = None
    position: int = 0
    active: bool = True
    model_config = ConfigDict(from_attributes=True)


class ReadDiner(UpdateDiner):
    group_id: UUID4
    household_id: UUID4
    model_config = ConfigDict(from_attributes=True)


class DinerPagination(PaginationBase):
    items: list[ReadDiner]


class DinerSelectionIn(MealieModel):
    mode: DinerSelectionMode = DinerSelectionMode.all
    diner_ids: list[UUID4] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selection(self):
        if self.mode == DinerSelectionMode.all and self.diner_ids:
            raise ValueError("dinerIds must be empty when mode is all")
        if self.mode == DinerSelectionMode.selected and not self.diner_ids:
            raise ValueError("at least one dinerId is required when mode is selected")
        if len(self.diner_ids) != len(set(self.diner_ids)):
            raise ValueError("dinerIds must be unique")
        return self


class DinerSelectionOut(MealieModel):
    mode: DinerSelectionMode
    diner_ids: list[UUID4]
    diners: list[DinerSummary]


class PreparationIntentMode(StrEnum):
    create = "create"
    existing = "existing"
    none = "none"


class PreparationIntent(MealieModel):
    mode: PreparationIntentMode
    preparation_id: UUID4 | None = None
    cook_date: date | None = None
    cook_diner_id: UUID4 | None = None

    @model_validator(mode="after")
    def validate_intent(self):
        if self.mode == PreparationIntentMode.create and self.cook_date is None:
            raise ValueError("cookDate is required when creating a preparation")
        if self.mode == PreparationIntentMode.existing and self.preparation_id is None:
            raise ValueError("preparationId is required when using an existing preparation")
        if self.mode == PreparationIntentMode.none and any(
            value is not None for value in (self.preparation_id, self.cook_date, self.cook_diner_id)
        ):
            raise ValueError("no preparation fields may be set when mode is none")
        return self


class CreateMealPreparation(MealieModel):
    recipe_id: UUID4
    cook_date: date
    cook_diner_id: UUID4 | None = None


class SaveMealPreparation(CreateMealPreparation):
    group_id: UUID4
    household_id: UUID4


class UpdateMealPreparation(CreateMealPreparation):
    id: UUID4


class LinkedMealPlanSummary(MealieModel):
    id: int
    date: date
    entry_type: str
    model_config = ConfigDict(from_attributes=True)


class ReadMealPreparation(UpdateMealPreparation):
    group_id: UUID4
    household_id: UUID4
    cook_diner: DinerSummary | None = None
    linked_meals: list[LinkedMealPlanSummary] = Field(default_factory=list, validation_alias="meal_entries")
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [
            joinedload(MealPlanPreparation.cook_diner),
            selectinload(MealPlanPreparation.meal_entries),
        ]


class MealPreparationPagination(PaginationBase):
    items: list[ReadMealPreparation]
