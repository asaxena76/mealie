from datetime import date
from functools import cached_property

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import UUID4

from mealie.routes._base import BaseCrudController, controller
from mealie.schema import mapper
from mealie.schema.meal_plan import (
    CreateDiner,
    CreateMealPreparation,
    DinerPagination,
    MealPreparationPagination,
    ReadDiner,
    ReadMealPreparation,
    SaveDiner,
    UpdateDiner,
    UpdateMealPreparation,
)
from mealie.schema.response.pagination import PaginationQuery
from mealie.services.household_services.meal_plan_service import MealPlanService
from mealie.services.query_filter.builder import QueryFilterBuilder

diner_router = APIRouter(prefix="/households/diners", tags=["Households: Diners"])
preparation_router = APIRouter(prefix="/households/meal-preparations", tags=["Households: Meal Preparations"])


@controller(diner_router)
class HouseholdDinerController(BaseCrudController):
    @diner_router.get("", response_model=DinerPagination)
    def get_all(self, q: PaginationQuery = Depends(PaginationQuery)):
        return self.repos.household_diners.page_all(pagination=q)

    @diner_router.post("", response_model=ReadDiner, status_code=status.HTTP_201_CREATED)
    def create_one(self, data: CreateDiner):
        self.checks.can_manage_household()
        save_data = mapper.cast(data, SaveDiner, group_id=self.group_id, household_id=self.household_id)
        try:
            return self.repos.household_diners.create(save_data)
        except Exception as error:
            raise HTTPException(status_code=409, detail="A diner with this name already exists") from error

    @diner_router.get("/{item_id}", response_model=ReadDiner)
    def get_one(self, item_id: UUID4):
        diner = self.repos.household_diners.get_one(item_id)
        if diner is None:
            raise HTTPException(status_code=404, detail="Diner not found")
        return diner

    @diner_router.put("/{item_id}", response_model=ReadDiner)
    def update_one(self, item_id: UUID4, data: UpdateDiner):
        self.checks.can_manage_household()
        if data.id != item_id:
            raise HTTPException(status_code=422, detail="Diner id does not match route")
        try:
            return self.repos.household_diners.update(
                item_id,
                {
                    **data.model_dump(exclude={"id"}),
                    "group_id": self.group_id,
                    "household_id": self.household_id,
                },
            )
        except Exception as error:
            raise HTTPException(status_code=409, detail="Diner could not be updated") from error

    @diner_router.delete("/{item_id}", response_model=ReadDiner)
    def delete_one(self, item_id: UUID4):
        self.checks.can_manage_household()
        result = self.repos.household_diners.get_one(item_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Diner not found")
        diner_model = self.repos.household_diners._query_one(item_id)
        if diner_model.meal_entries or diner_model.preparations:
            raise HTTPException(
                status_code=409,
                detail="Referenced diners must be deactivated instead of deleted",
            )
        self.repos.household_diners.delete(item_id)
        return result


@controller(preparation_router)
class MealPreparationController(BaseCrudController):
    @cached_property
    def service(self) -> MealPlanService:
        return MealPlanService(self.group_id, self.household_id, self.user.id, self.repos)

    @preparation_router.get("", response_model=MealPreparationPagination)
    def get_all(
        self,
        q: PaginationQuery = Depends(PaginationQuery),
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        if start_date or end_date:
            if start_date and end_date:
                date_filter = f"cook_date >= {start_date} AND cook_date <= {end_date}"
            elif start_date:
                date_filter = f"cook_date >= {start_date}"
            else:
                date_filter = f"cook_date <= {end_date}"
            q.query_filter = QueryFilterBuilder.combine_filters(q.query_filter, date_filter)
        return self.repos.meal_preparations.page_all(pagination=q)

    @preparation_router.post("", response_model=ReadMealPreparation, status_code=status.HTTP_201_CREATED)
    def create_one(self, data: CreateMealPreparation):
        try:
            return self.service.create_preparation(data)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @preparation_router.get("/{item_id}", response_model=ReadMealPreparation)
    def get_one(self, item_id: UUID4):
        preparation = self.repos.meal_preparations.get_one(item_id)
        if preparation is None:
            raise HTTPException(status_code=404, detail="Meal preparation not found")
        return preparation

    @preparation_router.put("/{item_id}", response_model=ReadMealPreparation)
    def update_one(self, item_id: UUID4, data: UpdateMealPreparation):
        if data.id != item_id:
            raise HTTPException(status_code=422, detail="Meal preparation id does not match route")
        try:
            return self.service.update_preparation(item_id, data)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @preparation_router.delete("/{item_id}", response_model=ReadMealPreparation)
    def delete_one(self, item_id: UUID4):
        try:
            return self.service.delete_preparation(item_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
