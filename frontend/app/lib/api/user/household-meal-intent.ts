import { BaseCRUDAPI } from "../base/base-clients";
import type {
  CreateDiner,
  CreateMealPreparation,
  ReadDiner,
  ReadMealPreparation,
  UpdateDiner,
  UpdateMealPreparation,
} from "~/lib/api/types/meal-plan";

const prefix = "/api/households";

export class HouseholdDinerAPI extends BaseCRUDAPI<CreateDiner, ReadDiner, UpdateDiner> {
  baseRoute = `${prefix}/diners`;
  itemRoute = (id: string | number) => `${this.baseRoute}/${id}`;
}

export class MealPreparationAPI extends BaseCRUDAPI<CreateMealPreparation, ReadMealPreparation, UpdateMealPreparation> {
  baseRoute = `${prefix}/meal-preparations`;
  itemRoute = (id: string | number) => `${this.baseRoute}/${id}`;
}
