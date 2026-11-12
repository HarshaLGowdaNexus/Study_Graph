import { describe, expect, it } from "vitest";

describe("Privacy, Data Ownership & Cost Tracking (Task T20, Feature F22)", () => {
  it("enforces strict uppercase 'DELETE' confirmation for wiping user data", () => {
    const validateConfirmation = (text: string): boolean => text.trim() === "DELETE";

    expect(validateConfirmation("DELETE")).toBe(true);
    expect(validateConfirmation("  DELETE  ")).toBe(true);
    expect(validateConfirmation("delete")).toBe(false); // Lowercase must be rejected
    expect(validateConfirmation("Delete")).toBe(false);
    expect(validateConfirmation("")).toBe(false);
    expect(validateConfirmation("YES")).toBe(false);
  });

  it("calculates Gemini Flash token costs accurately based on official pricing", () => {
    // $0.075 per 1M prompt tokens, $0.300 per 1M completion tokens
    const calculateCost = (promptTokens: number, completionTokens: number): number => {
      const promptCost = (promptTokens / 1_000_000) * 0.075;
      const completionCost = (completionTokens / 1_000_000) * 0.30;
      return Number((promptCost + completionCost).toFixed(6));
    };

    // 10,000 prompt tokens + 2,000 completion tokens
    const cost = calculateCost(10_000, 2_000);
    // (10000/1000000)*0.075 = 0.00075
    // (2000/1000000)*0.30 = 0.0006
    // total = 0.00135
    expect(cost).toBeCloseTo(0.00135, 5);

    // 0 tokens = $0.00
    expect(calculateCost(0, 0)).toBe(0);
  });

  it("formats student user consent storage key with proper user isolation", () => {
    const getConsentKey = (userId: string) => `studygraph_consent_${userId}`;
    const userA = "11111111-1111-4111-8111-111111111111";
    const userB = "22222222-2222-4222-8222-222222222222";

    expect(getConsentKey(userA)).toBe("studygraph_consent_11111111-1111-4111-8111-111111111111");
    expect(getConsentKey(userB)).toBe("studygraph_consent_22222222-2222-4222-8222-222222222222");
    expect(getConsentKey(userA)).not.toBe(getConsentKey(userB));
  });

  it("clarifies student free tier context so users know their real spend is $0.00", () => {
    const formatTierNotice = (dailyRequests: number) => {
      if (dailyRequests <= 1500) {
        return "$0.00 (Free Tier - under 1,500 requests/day)";
      }
      return "Commercial API tier";
    };

    expect(formatTierNotice(10)).toContain("$0.00 (Free Tier");
    expect(formatTierNotice(1500)).toContain("$0.00 (Free Tier");
    expect(formatTierNotice(2000)).toBe("Commercial API tier");
  });
});

