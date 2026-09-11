import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String, Table, UniqueConstraint, orm, true
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column

from mealie.db.models.recipe.tag import Tag, plan_rules_to_tags

from .._model_base import BaseMixins, FilterableColumn, SqlAlchemyBase
from .._model_utils.auto_init import auto_init
from .._model_utils.guid import GUID
from ..recipe.category import Category, plan_rules_to_categories

if TYPE_CHECKING:
    from ..group import Group
    from ..recipe import RecipeModel
    from ..users import User
    from .household import Household


meal_plan_entry_diners = Table(
    "meal_plan_entry_diners",
    SqlAlchemyBase.metadata,
    Column("meal_plan_id", Integer, ForeignKey("group_meal_plans.id", ondelete="CASCADE"), primary_key=True),
    Column("diner_id", GUID, ForeignKey("household_diners.id", ondelete="RESTRICT"), primary_key=True),
)

plan_rules_to_households = Table(
    "plan_rules_to_households",
    SqlAlchemyBase.metadata,
    Column("group_plan_rule_id", GUID, ForeignKey("group_meal_plan_rules.id"), index=True),
    Column("household_id", GUID, ForeignKey("households.id"), index=True),
    UniqueConstraint("group_plan_rule_id", "household_id", name="group_plan_rule_id_household_id_key"),
)


class GroupMealPlanRules(BaseMixins, SqlAlchemyBase):
    __tablename__ = "group_meal_plan_rules"

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    group_id: FilterableColumn[GUID | None] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID | None] = mapped_column(GUID, ForeignKey("households.id"), index=True)

    day: FilterableColumn[str] = mapped_column(
        String, nullable=False, default="unset"
    )  # "MONDAY", "TUESDAY", "WEDNESDAY", etc...
    entry_type: FilterableColumn[str] = mapped_column(
        String, nullable=False, default=""
    )  # "breakfast", "lunch", "dinner", etc ...
    query_filter_string: Mapped[str] = mapped_column(String, nullable=False, default="")

    # Old filters - deprecated in favor of query filter strings
    categories: Mapped[list[Category]] = orm.relationship(Category, secondary=plan_rules_to_categories)
    tags: Mapped[list[Tag]] = orm.relationship(Tag, secondary=plan_rules_to_tags)
    households: Mapped[list["Household"]] = orm.relationship("Household", secondary=plan_rules_to_households)

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class GroupMealPlan(SqlAlchemyBase, BaseMixins):
    __tablename__ = "group_meal_plans"

    date: FilterableColumn[datetime.date] = mapped_column(Date, index=True, nullable=False)
    entry_type: FilterableColumn[str] = mapped_column(String, index=True, nullable=False)
    title: FilterableColumn[str] = mapped_column(String, index=True, nullable=False)
    text: FilterableColumn[str] = mapped_column(String, nullable=False)

    group_id: FilterableColumn[GUID | None] = mapped_column(GUID, ForeignKey("groups.id"), index=True)
    group: Mapped[Optional["Group"]] = orm.relationship("Group", back_populates="mealplans")
    household_id: AssociationProxy[GUID] = association_proxy("user", "household_id")
    household: AssociationProxy["Household"] = association_proxy("user", "household")
    user_id: FilterableColumn[GUID | None] = mapped_column(GUID, ForeignKey("users.id"), index=True)
    user: Mapped[Optional["User"]] = orm.relationship("User", back_populates="mealplans")

    recipe_id: FilterableColumn[GUID | None] = mapped_column(GUID, ForeignKey("recipes.id"), index=True)
    recipe: Mapped[Optional["RecipeModel"]] = orm.relationship(
        "RecipeModel", back_populates="meal_entries", uselist=False
    )

    diner_mode: FilterableColumn[str] = mapped_column(
        String, nullable=False, default="all", server_default="all", index=True
    )
    diners: Mapped[list["HouseholdDiner"]] = orm.relationship(
        "HouseholdDiner", secondary=meal_plan_entry_diners, back_populates="meal_entries"
    )

    preparation_id: FilterableColumn[GUID | None] = mapped_column(
        GUID, ForeignKey("meal_plan_preparations.id", ondelete="SET NULL"), index=True
    )
    preparation: Mapped[Optional["MealPlanPreparation"]] = orm.relationship(
        "MealPlanPreparation", back_populates="meal_entries"
    )

    @property
    def diner_selection(self) -> dict:
        diners = self.diners
        if self.diner_mode == "all" and self.user and self.user.household:
            diners = [diner for diner in self.user.household.diners if diner.active]

        return {
            "mode": self.diner_mode,
            "diners": sorted(diners, key=lambda diner: (diner.position, diner.name.lower())),
            "diner_ids": [diner.id for diner in diners] if self.diner_mode == "selected" else [],
        }

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class HouseholdDiner(SqlAlchemyBase, BaseMixins):
    __tablename__ = "household_diners"
    __table_args__ = (UniqueConstraint("household_id", "name", name="household_diner_name_key"),)

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    group_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(
        GUID, ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: FilterableColumn[str] = mapped_column(String, nullable=False, index=True)
    abbreviation: FilterableColumn[str] = mapped_column(String(4), nullable=False)
    emoji: FilterableColumn[str | None] = mapped_column(String(16))
    color: FilterableColumn[str | None] = mapped_column(String(7))
    position: FilterableColumn[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    active: FilterableColumn[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true(), index=True
    )

    household: Mapped["Household"] = orm.relationship("Household", back_populates="diners")
    meal_entries: Mapped[list[GroupMealPlan]] = orm.relationship(
        GroupMealPlan, secondary=meal_plan_entry_diners, back_populates="diners"
    )
    preparations: Mapped[list["MealPlanPreparation"]] = orm.relationship(
        "MealPlanPreparation", back_populates="cook_diner"
    )

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class MealPlanPreparation(SqlAlchemyBase, BaseMixins):
    __tablename__ = "meal_plan_preparations"

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    group_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(
        GUID, ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipe_id: FilterableColumn[GUID] = mapped_column(
        GUID, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cook_date: FilterableColumn[datetime.date] = mapped_column(Date, nullable=False, index=True)
    cook_diner_id: FilterableColumn[GUID | None] = mapped_column(
        GUID, ForeignKey("household_diners.id", ondelete="SET NULL"), index=True
    )

    recipe: Mapped["RecipeModel"] = orm.relationship("RecipeModel")
    cook_diner: Mapped[HouseholdDiner | None] = orm.relationship(HouseholdDiner, back_populates="preparations")
    meal_entries: Mapped[list[GroupMealPlan]] = orm.relationship(GroupMealPlan, back_populates="preparation")

    @auto_init()
    def __init__(self, **_) -> None:
        pass
