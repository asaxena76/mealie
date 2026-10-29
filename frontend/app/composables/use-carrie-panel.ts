import { addDays, format, startOfWeek } from "date-fns";
import type { CarrieContext } from "~/lib/api/types/carrie";

export function currentCarrieWeek(now = new Date()): CarrieContext {
  const start = startOfWeek(now, { weekStartsOn: 1 });
  return { startDate: format(start, "yyyy-MM-dd"), endDate: format(addDays(start, 6), "yyyy-MM-dd"), dinerIds: [], includeCooking: true };
}

export function useCarriePanel() {
  const open = useState<boolean>("carrie-panel-open", () => false);
  const planner = useState<{ context: CarrieContext; dinerLabel: string } | null>("carrie-panel-planner", () => null);
  return { open, planner };
}
