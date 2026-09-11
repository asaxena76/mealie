"""add meal plan intent metadata

Revision ID: a84ce91d2f70
Revises: 4b91d3a7c0e2
Create Date: 2026-09-10 06:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

import mealie.db.migration_types

revision = "a84ce91d2f70"
down_revision: str | None = "4b91d3a7c0e2"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "household_diners",
        sa.Column("id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("group_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("household_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("abbreviation", sa.String(length=4), nullable=False),
        sa.Column("emoji", sa.String(length=16), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("update_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "name", name="household_diner_name_key"),
    )
    with op.batch_alter_table("household_diners") as batch_op:
        batch_op.create_index(batch_op.f("ix_household_diners_active"), ["active"])
        batch_op.create_index(batch_op.f("ix_household_diners_created_at"), ["created_at"])
        batch_op.create_index(batch_op.f("ix_household_diners_group_id"), ["group_id"])
        batch_op.create_index(batch_op.f("ix_household_diners_household_id"), ["household_id"])
        batch_op.create_index(batch_op.f("ix_household_diners_name"), ["name"])
        batch_op.create_index(batch_op.f("ix_household_diners_position"), ["position"])

    op.create_table(
        "meal_plan_preparations",
        sa.Column("id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("group_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("household_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("recipe_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("cook_date", sa.Date(), nullable=False),
        sa.Column("cook_diner_id", mealie.db.migration_types.GUID(), nullable=True),
        sa.Column("created_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("update_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["cook_diner_id"], ["household_diners.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("meal_plan_preparations") as batch_op:
        batch_op.create_index(batch_op.f("ix_meal_plan_preparations_cook_date"), ["cook_date"])
        batch_op.create_index(batch_op.f("ix_meal_plan_preparations_cook_diner_id"), ["cook_diner_id"])
        batch_op.create_index(batch_op.f("ix_meal_plan_preparations_created_at"), ["created_at"])
        batch_op.create_index(batch_op.f("ix_meal_plan_preparations_group_id"), ["group_id"])
        batch_op.create_index(batch_op.f("ix_meal_plan_preparations_household_id"), ["household_id"])
        batch_op.create_index(batch_op.f("ix_meal_plan_preparations_recipe_id"), ["recipe_id"])

    with op.batch_alter_table("group_meal_plans") as batch_op:
        batch_op.add_column(sa.Column("diner_mode", sa.String(), server_default="all", nullable=False))
        batch_op.add_column(sa.Column("preparation_id", mealie.db.migration_types.GUID(), nullable=True))
        batch_op.create_foreign_key(
            "group_meal_plans_preparation_id_fkey",
            "meal_plan_preparations",
            ["preparation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(batch_op.f("ix_group_meal_plans_diner_mode"), ["diner_mode"])
        batch_op.create_index(batch_op.f("ix_group_meal_plans_preparation_id"), ["preparation_id"])

    op.create_table(
        "meal_plan_entry_diners",
        sa.Column("meal_plan_id", sa.Integer(), nullable=False),
        sa.Column("diner_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.ForeignKeyConstraint(["diner_id"], ["household_diners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["meal_plan_id"], ["group_meal_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("meal_plan_id", "diner_id"),
    )


def downgrade() -> None:
    op.drop_table("meal_plan_entry_diners")

    with op.batch_alter_table("group_meal_plans") as batch_op:
        batch_op.drop_index(batch_op.f("ix_group_meal_plans_preparation_id"))
        batch_op.drop_index(batch_op.f("ix_group_meal_plans_diner_mode"))
        batch_op.drop_constraint("group_meal_plans_preparation_id_fkey", type_="foreignkey")
        batch_op.drop_column("preparation_id")
        batch_op.drop_column("diner_mode")

    with op.batch_alter_table("meal_plan_preparations") as batch_op:
        batch_op.drop_index(batch_op.f("ix_meal_plan_preparations_recipe_id"))
        batch_op.drop_index(batch_op.f("ix_meal_plan_preparations_household_id"))
        batch_op.drop_index(batch_op.f("ix_meal_plan_preparations_group_id"))
        batch_op.drop_index(batch_op.f("ix_meal_plan_preparations_created_at"))
        batch_op.drop_index(batch_op.f("ix_meal_plan_preparations_cook_diner_id"))
        batch_op.drop_index(batch_op.f("ix_meal_plan_preparations_cook_date"))
    op.drop_table("meal_plan_preparations")

    with op.batch_alter_table("household_diners") as batch_op:
        batch_op.drop_index(batch_op.f("ix_household_diners_position"))
        batch_op.drop_index(batch_op.f("ix_household_diners_name"))
        batch_op.drop_index(batch_op.f("ix_household_diners_household_id"))
        batch_op.drop_index(batch_op.f("ix_household_diners_group_id"))
        batch_op.drop_index(batch_op.f("ix_household_diners_created_at"))
        batch_op.drop_index(batch_op.f("ix_household_diners_active"))
    op.drop_table("household_diners")
