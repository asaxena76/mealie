from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.utils import api_routes
from tests.utils.fixture_schemas import TestUser


def create_diner(api_client: TestClient, user: TestUser, name: str, abbreviation: str, position: int) -> dict:
    response = api_client.post(
        api_routes.households_diners,
        headers=user.token,
        json={
            "name": name,
            "abbreviation": abbreviation,
            "emoji": "🍽️",
            "color": "#336699",
            "position": position,
            "active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_meal_plan_diners_and_shared_preparation(api_client: TestClient, unique_user: TestUser):
    diner_one = create_diner(api_client, unique_user, "Alex", "AX", 0)
    diner_two = create_diner(api_client, unique_user, "Blair", "BL", 1)

    recipe_response = api_client.post(
        api_routes.recipes,
        headers=unique_user.token,
        json={"name": "Weekend Test Stew"},
    )
    assert recipe_response.status_code == 201
    recipe_response = api_client.get(
        api_routes.recipes_slug(recipe_response.json()),
        headers=unique_user.token,
    )
    assert recipe_response.status_code == 200
    recipe_id = recipe_response.json()["id"]

    cook_date = datetime.now(UTC).date() + timedelta(days=3)
    first_meal = api_client.post(
        api_routes.households_mealplans,
        headers=unique_user.token,
        json={
            "date": cook_date.isoformat(),
            "entryType": "dinner",
            "recipeId": recipe_id,
            "dinerSelection": {"mode": "all", "dinerIds": []},
            "preparationIntent": {
                "mode": "create",
                "cookDate": cook_date.isoformat(),
                "cookDinerId": diner_one["id"],
            },
        },
    )
    assert first_meal.status_code == 201
    first_data = first_meal.json()
    assert [diner["name"] for diner in first_data["dinerSelection"]["diners"]] == ["Alex", "Blair"]
    assert first_data["preparation"]["cookDiner"]["id"] == diner_one["id"]
    preparation_id = first_data["preparation"]["id"]

    second_meal = api_client.post(
        api_routes.households_mealplans,
        headers=unique_user.token,
        json={
            "date": (cook_date + timedelta(days=1)).isoformat(),
            "entryType": "dinner",
            "recipeId": recipe_id,
            "dinerSelection": {"mode": "selected", "dinerIds": [diner_two["id"]]},
            "preparationIntent": {"mode": "existing", "preparationId": preparation_id},
        },
    )
    assert second_meal.status_code == 201
    second_data = second_meal.json()
    assert second_data["dinerSelection"]["mode"] == "selected"
    assert [diner["id"] for diner in second_data["dinerSelection"]["diners"]] == [diner_two["id"]]
    assert second_data["dinerSelection"]["dinerIds"] == [diner_two["id"]]
    assert second_data["preparation"]["id"] == preparation_id

    round_trip = api_client.put(
        api_routes.households_mealplans_item_id(second_data["id"]),
        headers=unique_user.token,
        json=second_data,
    )
    assert round_trip.status_code == 200
    assert round_trip.json()["dinerSelection"]["dinerIds"] == [diner_two["id"]]
    assert round_trip.json()["preparation"]["id"] == preparation_id

    preparation_response = api_client.get(
        api_routes.households_meal_preparations_item_id(preparation_id),
        headers=unique_user.token,
    )
    assert preparation_response.status_code == 200
    linked_meal_ids = {meal["id"] for meal in preparation_response.json()["linkedMeals"]}
    assert linked_meal_ids == {first_data["id"], second_data["id"]}


def test_diner_selection_rejects_other_household(
    api_client: TestClient,
    unique_user: TestUser,
    h2_user: TestUser,
):
    other_diner = h2_user.repos.household_diners.create(
        {
            "name": "Casey",
            "abbreviation": "CY",
            "position": 0,
            "active": True,
            "group_id": h2_user.group_id,
            "household_id": h2_user.household_id,
        }
    )

    response = api_client.post(
        api_routes.households_mealplans,
        headers=unique_user.token,
        json={
            "date": datetime.now(UTC).date().isoformat(),
            "entryType": "lunch",
            "title": "Packed lunch",
            "dinerSelection": {"mode": "selected", "dinerIds": [str(other_diner.id)]},
        },
    )

    assert response.status_code == 422
    assert "do not belong to this household" in response.json()["detail"]
