/**
 * Platform configuration and validation.
 *
 * Corrected taxonomy from user:
 *   AJBell = SIPP (personal pension)
 *   Aviva  = Company pension
 *   IG     = Personal + ISA + spread betting
 *   NS&I   = Cash savings (premium bonds)
 */

export type PlatformName = "ajbell" | "aviva" | "ig" | "nsandi"
export type TradeMode = "shares" | "spreadbet" | "funds" | "cash"

export interface PlatformConfig {
  name: string
  type: string
  taxWrapper: string
  spreadBet: boolean
  availableModes: TradeMode[]
  minOrder?: number
  commission?: number
  stampDuty: number
  marginFactor?: number
  marginIsEstimate?: boolean // true if margin is a generic fallback
  overnightRate?: number
  accessNote: string
  taxNote: string
}

export const PLATFORMS: Record<PlatformName, PlatformConfig> = {
  ajbell: {
    name: "AJBell",
    type: "SIPP",
    taxWrapper: "Pension (25% tax-free at 55+)",
    spreadBet: false,
    availableModes: ["shares", "funds", "trusts"],
    minOrder: 1,
    commission: 9.95,
    stampDuty: 0.005,
    accessNote: "Locked until age 55. Early withdrawal penalties apply.",
    taxNote: "No CGT inside SIPP. Tax relief on contributions.",
  },
  aviva: {
    name: "Aviva",
    type: "Company pension",
    taxWrapper: "Workplace pension",
    spreadBet: false,
    availableModes: ["funds"],
    commission: 7.5,
    stampDuty: 0,
    accessNote: "Employer-matched contributions. Verify scheme allows direct equity.",
    taxNote: "No CGT inside pension. Tax relief on contributions.",
  },
  ig: {
    name: "IG",
    type: "Personal + ISA",
    taxWrapper: "ISA available (£20k/year)",
    spreadBet: true,
    availableModes: ["shares", "spreadbet"],
    minOrder: 1,
    commission: 0,
    stampDuty: 0,
    marginFactor: 0.05,
    marginIsEstimate: true,
    overnightRate: 0.025,
    accessNote: "No pension wrapper. ISA for tax-free gains.",
    taxNote: "CGT outside ISA. Spread betting currently CGT-free.",
  },
  nsandi: {
    name: "NS&I",
    type: "Cash savings",
    taxWrapper: "None",
    spreadBet: false,
    availableModes: ["cash"],
    stampDuty: 0,
    accessNote: "Premium bonds only. Prize-based, no guaranteed return.",
    taxNote: "Winnings tax-free but not guaranteed.",
  },
}

export function getPlatform(name: string): PlatformConfig | null {
  const key = name.toLowerCase() as PlatformName
  return PLATFORMS[key] ?? null
}

export function validateMode(
  platformName: string,
  mode: TradeMode,
): { ok: boolean; error?: string } {
  const platform = getPlatform(platformName)
  if (!platform) {
    return { ok: false, error: `Unknown platform: ${platformName}` }
  }

  if (!platform.availableModes.includes(mode)) {
    const allowed = platform.availableModes.join(", ")
    return {
      ok: false,
      error: `${platform.name} does not support ${mode}. Available: ${allowed}`,
    }
  }

  if (mode === "spreadbet" && !platform.spreadBet) {
    return {
      ok: false,
      error: `Spread betting is only available on IG. Use --platform ig --mode spreadbet`,
    }
  }

  return { ok: true }
}
