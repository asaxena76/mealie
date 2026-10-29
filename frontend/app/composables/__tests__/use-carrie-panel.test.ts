import { describe, expect, it } from "vitest";
import { currentCarrieWeek } from "../use-carrie-panel";

describe("Carrie context outside the planner", () => {
  it("uses the local Monday–Sunday week with everyone and cooking included", () => {
    expect(currentCarrieWeek(new Date(2026, 9, 28, 12))).toEqual({
      startDate: "2026-10-26", endDate: "2026-11-01", dinerIds: [], includeCooking: true,
    });
  });

  it("keeps Sunday in the previous week across a year boundary", () => {
    expect(currentCarrieWeek(new Date(2027, 0, 3, 12)).startDate).toBe("2026-12-28");
    expect(currentCarrieWeek(new Date(2027, 0, 4, 12)).startDate).toBe("2027-01-04");
  });
});
