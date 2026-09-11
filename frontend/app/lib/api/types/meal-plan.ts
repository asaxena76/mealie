/* tslint:disable */

/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export type PlanEntryType = "breakfast" | "lunch" | "dinner" | "side" | "snack" | "drink" | "dessert";
export type DinerSelectionMode = "all" | "selected";
export type PreparationIntentMode = "create" | "existing" | "none";
export type PlanRulesDay = "monday" | "tuesday" | "wednesday" | "thursday" | "friday" | "saturday" | "sunday" | "unset";
export type PlanRulesType = "breakfast" | "lunch" | "dinner" | "side" | "snack" | "drink" | "dessert" | "unset";
export type LogicalOperator = "AND" | "OR";
export type RelationalKeyword = "IS" | "IS NOT" | "IN" | "NOT IN" | "CONTAINS ALL" | "LIKE" | "NOT LIKE";
export type RelationalOperator = "=" | "<>" | ">" | "<" | ">=" | "<=";

export interface CreateDiner {
  name: string;
  abbreviation: string;
  emoji?: string | null;
  color?: string | null;
  position?: number;
  active?: boolean;
}
export interface CreateMealPreparation {
  recipeId: string;
  cookDate: string;
  cookDinerId?: string | null;
}
export interface CreatePlanEntry {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
  dinerSelection?: DinerSelectionIn | null;
  preparationIntent?: PreparationIntent | null;
}
export interface DinerSelectionIn {
  mode?: DinerSelectionMode;
  dinerIds?: string[];
}
export interface PreparationIntent {
  mode: PreparationIntentMode;
  preparationId?: string | null;
  cookDate?: string | null;
  cookDinerId?: string | null;
}
export interface CreateRandomEntry {
  date: string;
  entryType?: PlanEntryType;
}
export interface DinerBase {
  name: string;
  abbreviation: string;
  emoji?: string | null;
  color?: string | null;
  position?: number;
  active?: boolean;
}
export interface DinerSelectionOut {
  mode: DinerSelectionMode;
  dinerIds: string[];
  diners: DinerSummary[];
}
export interface DinerSummary {
  id: string;
  name: string;
  abbreviation: string;
  emoji?: string | null;
  color?: string | null;
  position?: number;
  active?: boolean;
}
export interface LinkedMealPlanSummary {
  id: number;
  date: string;
  entryType: string;
}
export interface ListItem {
  title?: string | null;
  text?: string;
  quantity?: number;
  checked?: boolean;
}
export interface PlanEntryBase {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
}
export interface PlanRulesCreate {
  day?: PlanRulesDay;
  entryType?: PlanRulesType;
  queryFilterString?: string;
}
export interface PlanRulesOut {
  day?: PlanRulesDay;
  entryType?: PlanRulesType;
  queryFilterString?: string;
  groupId: string;
  householdId: string;
  id: string;
  queryFilter?: QueryFilterJSON;
}
export interface QueryFilterJSON {
  parts?: QueryFilterJSONPart[];
}
export interface QueryFilterJSONPart {
  leftParenthesis?: string | null;
  rightParenthesis?: string | null;
  logicalOperator?: LogicalOperator | null;
  attributeName?: string | null;
  relationalOperator?: RelationalKeyword | RelationalOperator | null;
  value?: string | string[] | null;
  [k: string]: unknown;
}
export interface PlanRulesSave {
  day?: PlanRulesDay;
  entryType?: PlanRulesType;
  queryFilterString?: string;
  groupId: string;
  householdId: string;
}
export interface ReadDiner {
  name: string;
  abbreviation: string;
  emoji?: string | null;
  color?: string | null;
  position?: number;
  active?: boolean;
  id: string;
  groupId: string;
  householdId: string;
}
export interface ReadMealPreparation {
  recipeId: string;
  cookDate: string;
  cookDinerId?: string | null;
  id: string;
  groupId: string;
  householdId: string;
  cookDiner?: DinerSummary | null;
  linkedMeals?: LinkedMealPlanSummary[];
}
export interface ReadPlanEntry {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
  id: number;
  groupId: string;
  userId: string;
  householdId: string;
  recipe?: RecipeSummary | null;
  dinerSelection: DinerSelectionOut;
  preparation?: ReadMealPreparation | null;
}
export interface RecipeSummary {
  id?: string | null;
  userId?: string;
  householdId?: string;
  groupId?: string;
  name?: string | null;
  slug?: string;
  image?: unknown;
  recipeServings?: number;
  recipeYieldQuantity?: number;
  recipeYield?: string | null;
  totalTime?: string | null;
  prepTime?: string | null;
  cookTime?: string | null;
  performTime?: string | null;
  description?: string | null;
  recipeCategory?: RecipeCategory[] | null;
  tags?: RecipeTag[] | null;
  tools?: RecipeTool[];
  rating?: number | null;
  orgURL?: string | null;
  dateAdded?: string | null;
  dateUpdated?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  lastMade?: string | null;
}
export interface RecipeCategory {
  id?: string | null;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
}
export interface RecipeTag {
  id?: string | null;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
}
export interface RecipeTool {
  id: string;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
  householdsWithTool?: string[];
}
export interface SaveDiner {
  name: string;
  abbreviation: string;
  emoji?: string | null;
  color?: string | null;
  position?: number;
  active?: boolean;
  groupId: string;
  householdId: string;
}
export interface SaveMealPreparation {
  recipeId: string;
  cookDate: string;
  cookDinerId?: string | null;
  groupId: string;
  householdId: string;
}
export interface SavePlanEntry {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
  dinerSelection?: DinerSelectionIn | null;
  preparationIntent?: PreparationIntent | null;
  groupId: string;
  userId: string;
}
export interface ShoppingListIn {
  name: string;
  group?: string | null;
  items: ListItem[];
}
export interface ShoppingListOut {
  name: string;
  group?: string | null;
  items: ListItem[];
  id: number;
}
export interface UpdateDiner {
  name: string;
  abbreviation: string;
  emoji?: string | null;
  color?: string | null;
  position?: number;
  active?: boolean;
  id: string;
}
export interface UpdateMealPreparation {
  recipeId: string;
  cookDate: string;
  cookDinerId?: string | null;
  id: string;
}
export interface UpdatePlanEntry {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
  dinerSelection?: DinerSelectionIn | null;
  preparationIntent?: PreparationIntent | null;
  id: number;
  groupId: string;
  userId: string;
}
