from datetime import date
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator
from pydantic_core.core_schema import ValidationInfo
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.household import GroupMealPlan, Household, MealPlanPreparation
from mealie.db.models.recipe import RecipeModel
from mealie.db.models.users.users import User
from mealie.schema._mealie import MealieModel
from mealie.schema.recipe.recipe import RecipeSummary
from mealie.schema.response.pagination import PaginationBase

from .meal_intent import DinerSelectionIn, DinerSelectionOut, PreparationIntent, ReadMealPreparation


class PlanEntryType(StrEnum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"
    side = "side"
    snack = "snack"
    drink = "drink"
    dessert = "dessert"


class CreateRandomEntry(MealieModel):
    date: date
    entry_type: PlanEntryType = PlanEntryType.dinner


class PlanEntryBase(MealieModel):
    date: date
    entry_type: PlanEntryType = PlanEntryType.breakfast
    title: str = ""
    text: str = ""
    recipe_id: Annotated[UUID | None, Field(validate_default=True)] = None

    @field_validator("recipe_id")
    @classmethod
    def id_or_title(cls, value, info: ValidationInfo):
        if bool(value) is False and bool(info.data["title"]) is False:
            raise ValueError(f"`recipe_id={value}` or `title={info.data['title']}` must be provided")

        return value


class CreatePlanEntry(PlanEntryBase):
    diner_selection: DinerSelectionIn | None = None
    preparation_intent: PreparationIntent | None = None


class UpdatePlanEntry(CreatePlanEntry):
    id: int
    group_id: UUID
    user_id: UUID


class SavePlanEntry(CreatePlanEntry):
    group_id: UUID
    user_id: UUID
    model_config = ConfigDict(from_attributes=True)


class ReadPlanEntry(PlanEntryBase):
    id: int
    group_id: UUID
    user_id: UUID
    household_id: UUID
    recipe: RecipeSummary | None = None
    diner_selection: DinerSelectionOut
    preparation: ReadMealPreparation | None = None
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [
            selectinload(GroupMealPlan.recipe).joinedload(RecipeModel.recipe_category),
            selectinload(GroupMealPlan.recipe).joinedload(RecipeModel.tags),
            selectinload(GroupMealPlan.recipe).joinedload(RecipeModel.tools),
            selectinload(GroupMealPlan.user).joinedload(User.household).selectinload(Household.diners),
            selectinload(GroupMealPlan.diners),
            selectinload(GroupMealPlan.preparation).joinedload(MealPlanPreparation.cook_diner),
            selectinload(GroupMealPlan.preparation).selectinload(MealPlanPreparation.meal_entries),
        ]


class PlanEntryPagination(PaginationBase):
    items: list[ReadPlanEntry]
