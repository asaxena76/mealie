from __future__ import annotations

from pydantic import UUID4
from sqlalchemy import select

from mealie.db.models.household import GroupMealPlan, HouseholdDiner, MealPlanPreparation
from mealie.db.models.recipe import RecipeModel
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.meal_plan import (
    CreateMealPreparation,
    CreatePlanEntry,
    DinerSelectionIn,
    DinerSelectionMode,
    PreparationIntent,
    PreparationIntentMode,
    ReadMealPreparation,
    ReadPlanEntry,
    UpdateMealPreparation,
    UpdatePlanEntry,
)
from mealie.services._base_service import BaseService


class MealPlanService(BaseService):
    def __init__(self, group_id: UUID4, household_id: UUID4, user_id: UUID4, repos: AllRepositories):
        self.group_id = group_id
        self.household_id = household_id
        self.user_id = user_id
        self.repos = repos
        self.session = repos.session
        super().__init__()

    def _meal_model(self, meal_id: int) -> GroupMealPlan:
        meal = self.session.scalar(
            select(GroupMealPlan).where(
                GroupMealPlan.id == meal_id,
                GroupMealPlan.group_id == self.group_id,
                GroupMealPlan.user.has(household_id=self.household_id),
            )
        )
        if meal is None:
            raise ValueError("Meal-plan entry not found")
        return meal

    def _diner_models(self, selection: DinerSelectionIn | None) -> tuple[str, list[HouseholdDiner]]:
        if selection is None or selection.mode == DinerSelectionMode.all:
            return DinerSelectionMode.all.value, []

        diners = list(
            self.session.scalars(
                select(HouseholdDiner).where(
                    HouseholdDiner.id.in_(selection.diner_ids),
                    HouseholdDiner.group_id == self.group_id,
                    HouseholdDiner.household_id == self.household_id,
                    HouseholdDiner.active.is_(True),
                )
            )
        )
        if len(diners) != len(selection.diner_ids):
            raise ValueError("One or more diners are inactive or do not belong to this household")

        active_ids = set(
            self.session.scalars(
                select(HouseholdDiner.id).where(
                    HouseholdDiner.group_id == self.group_id,
                    HouseholdDiner.household_id == self.household_id,
                    HouseholdDiner.active.is_(True),
                )
            )
        )
        if active_ids and active_ids == set(selection.diner_ids):
            return DinerSelectionMode.all.value, []

        return DinerSelectionMode.selected.value, diners

    def _cook_diner(self, diner_id: UUID4 | None) -> HouseholdDiner | None:
        if diner_id is None:
            return None
        diner = self.session.scalar(
            select(HouseholdDiner).where(
                HouseholdDiner.id == diner_id,
                HouseholdDiner.group_id == self.group_id,
                HouseholdDiner.household_id == self.household_id,
                HouseholdDiner.active.is_(True),
            )
        )
        if diner is None:
            raise ValueError("Cook must be an active diner in this household")
        return diner

    def _recipe(self, recipe_id: UUID4) -> RecipeModel:
        recipe = self.session.scalar(
            select(RecipeModel).where(RecipeModel.id == recipe_id, RecipeModel.group_id == self.group_id)
        )
        if recipe is None:
            raise ValueError("Recipe not found in this group")
        return recipe

    def _preparation_model(self, preparation_id: UUID4) -> MealPlanPreparation:
        preparation = self.session.scalar(
            select(MealPlanPreparation).where(
                MealPlanPreparation.id == preparation_id,
                MealPlanPreparation.group_id == self.group_id,
                MealPlanPreparation.household_id == self.household_id,
            )
        )
        if preparation is None:
            raise ValueError("Meal preparation not found")
        return preparation

    def _resolve_preparation(
        self,
        intent: PreparationIntent | None,
        *,
        recipe_id: UUID4 | None,
        meal_date,
        create_default: bool,
    ) -> MealPlanPreparation | None:
        if recipe_id is None:
            if intent and intent.mode != PreparationIntentMode.none:
                raise ValueError("Only recipe-backed meals can have a cooking intention")
            return None

        if intent is None:
            if not create_default:
                return None
            intent = PreparationIntent(mode=PreparationIntentMode.create, cook_date=meal_date)

        if intent.mode == PreparationIntentMode.none:
            return None

        if intent.mode == PreparationIntentMode.existing:
            preparation = self._preparation_model(intent.preparation_id)  # type: ignore[arg-type]
            if preparation.recipe_id != recipe_id:
                raise ValueError("The selected preparation belongs to a different recipe")
            cook_date = intent.cook_date if "cook_date" in intent.model_fields_set else preparation.cook_date
            if cook_date is None or cook_date > meal_date:
                raise ValueError("A meal cannot be eaten before its preparation date")
            if any(linked_meal.date < cook_date for linked_meal in preparation.meal_entries):
                raise ValueError("Cooking date cannot be later than a linked eating date")
            preparation.cook_date = cook_date
            if "cook_diner_id" in intent.model_fields_set:
                cook_diner = self._cook_diner(intent.cook_diner_id)
                preparation.cook_diner_id = cook_diner.id if cook_diner else None
            return preparation

        self._recipe(recipe_id)
        cook_diner = self._cook_diner(intent.cook_diner_id)
        if intent.cook_date is None or intent.cook_date > meal_date:
            raise ValueError("A meal cannot be eaten before its preparation date")

        preparation = MealPlanPreparation(
            session=self.session,
            group_id=self.group_id,
            household_id=self.household_id,
            recipe_id=recipe_id,
            cook_date=intent.cook_date,
            cook_diner_id=cook_diner.id if cook_diner else None,
        )
        self.session.add(preparation)
        self.session.flush()
        return preparation

    def _delete_if_orphaned(self, preparation: MealPlanPreparation | None) -> None:
        if preparation is None:
            return
        self.session.flush()
        self.session.refresh(preparation, attribute_names=["meal_entries"])
        if not preparation.meal_entries:
            self.session.delete(preparation)

    def create_meal(self, data: CreatePlanEntry) -> ReadPlanEntry:
        try:
            diner_mode, diners = self._diner_models(data.diner_selection)
            preparation = self._resolve_preparation(
                data.preparation_intent,
                recipe_id=data.recipe_id,
                meal_date=data.date,
                create_default=True,
            )
            meal = GroupMealPlan(
                session=self.session,
                date=data.date,
                entry_type=data.entry_type.value,
                title=data.title,
                text=data.text,
                group_id=self.group_id,
                user_id=self.user_id,
                recipe_id=data.recipe_id,
                diner_mode=diner_mode,
                preparation_id=preparation.id if preparation else None,
            )
            meal.diners = diners
            meal.preparation = preparation
            self.session.add(meal)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        result = self.repos.meals.get_one(meal.id)
        if result is None:
            raise ValueError("Created meal-plan entry could not be loaded")
        return result

    def update_meal(self, meal_id: int, data: UpdatePlanEntry) -> ReadPlanEntry:
        try:
            meal = self._meal_model(meal_id)
            old_preparation = meal.preparation

            meal.date = data.date
            meal.entry_type = data.entry_type.value
            meal.title = data.title
            meal.text = data.text
            meal.recipe_id = data.recipe_id

            if "diner_selection" in data.model_fields_set:
                diner_mode, diners = self._diner_models(data.diner_selection)
                meal.diner_mode = diner_mode
                meal.diners = diners

            if "preparation_intent" in data.model_fields_set:
                preparation = self._resolve_preparation(
                    data.preparation_intent,
                    recipe_id=data.recipe_id,
                    meal_date=data.date,
                    create_default=False,
                )
                meal.preparation = preparation
                meal.preparation_id = preparation.id if preparation else None
            elif meal.preparation:
                if meal.recipe_id != meal.preparation.recipe_id:
                    raise ValueError("Remove or replace the cooking intention before changing the recipe")
                if meal.date < meal.preparation.cook_date:
                    raise ValueError("A meal cannot be eaten before its preparation date")

            self.session.flush()
            if old_preparation is not meal.preparation:
                self._delete_if_orphaned(old_preparation)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        result = self.repos.meals.get_one(meal_id)
        if result is None:
            raise ValueError("Updated meal-plan entry could not be loaded")
        return result

    def delete_meal(self, meal_id: int) -> ReadPlanEntry:
        result = self.repos.meals.get_one(meal_id)
        if result is None:
            raise ValueError("Meal-plan entry not found")

        try:
            meal = self._meal_model(meal_id)
            preparation = meal.preparation
            meal.preparation = None
            self.session.delete(meal)
            self.session.flush()
            self._delete_if_orphaned(preparation)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return result

    def create_preparation(self, data: CreateMealPreparation) -> ReadMealPreparation:
        self._recipe(data.recipe_id)
        cook = self._cook_diner(data.cook_diner_id)
        result = self.repos.meal_preparations.create(
            {
                **data.model_dump(),
                "group_id": self.group_id,
                "household_id": self.household_id,
                "cook_diner_id": cook.id if cook else None,
            }
        )
        return result

    def update_preparation(self, preparation_id: UUID4, data: UpdateMealPreparation) -> ReadMealPreparation:
        preparation = self._preparation_model(preparation_id)
        self._recipe(data.recipe_id)
        cook = self._cook_diner(data.cook_diner_id)
        if any(meal.date < data.cook_date for meal in preparation.meal_entries):
            raise ValueError("Cooking date cannot be later than a linked eating date")
        if any(meal.recipe_id != data.recipe_id for meal in preparation.meal_entries):
            raise ValueError("Preparation recipe must match every linked meal")

        result = self.repos.meal_preparations.update(
            preparation_id,
            {
                "group_id": self.group_id,
                "household_id": self.household_id,
                "recipe_id": data.recipe_id,
                "cook_date": data.cook_date,
                "cook_diner_id": cook.id if cook else None,
            },
        )
        return result

    def delete_preparation(self, preparation_id: UUID4) -> ReadMealPreparation:
        preparation = self._preparation_model(preparation_id)
        if preparation.meal_entries:
            raise ValueError("Unlink all meals before deleting this preparation")
        result = self.repos.meal_preparations.get_one(preparation_id)
        if result is None:
            raise ValueError("Meal preparation not found")
        self.repos.meal_preparations.delete(preparation_id)
        return result
