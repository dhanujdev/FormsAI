import type { FormField } from "./types"

export const formSchema: FormField[] = [
  { id: "full_name", label: "Full legal name", type: "text", required: true, evidence: false },
  { id: "dob", label: "Date of birth", type: "date", required: true, evidence: false },
  { id: "phone", label: "Phone number", type: "text", required: true, evidence: false },
  { id: "email", label: "Email", type: "email", required: true, evidence: false, verifier: "domain_check" },
  { id: "address_line1", label: "Street address", type: "text", required: true, evidence: true, docTypes: ["lease", "utility_bill"], verifier: "address_normalize" },
  { id: "city", label: "City", type: "text", required: true, evidence: true, docTypes: ["lease", "utility_bill"], verifier: "address_normalize" },
  { id: "state", label: "State (2-letter)", type: "text", required: true, evidence: true, docTypes: ["lease", "utility_bill"], verifier: "address_normalize" },
  { id: "zip", label: "ZIP code", type: "text", required: true, evidence: true, docTypes: ["lease", "utility_bill"], verifier: "address_normalize" },
  { id: "household_size", label: "Household size", type: "number", required: true, evidence: false },
  { id: "landlord_name", label: "Landlord name", type: "text", required: true, evidence: true, docTypes: ["lease", "landlord_letter"] },
  { id: "landlord_contact", label: "Landlord contact (phone/email)", type: "text", required: true, evidence: true, docTypes: ["lease", "landlord_letter"], verifier: "domain_check" },
  { id: "monthly_rent", label: "Monthly rent (USD)", type: "text", required: true, evidence: true, docTypes: ["lease", "rent_ledger"] },
  { id: "employer_name", label: "Employer name (if employed)", type: "text", required: false, evidence: true, docTypes: ["paystub", "income_verification"] },
  { id: "monthly_gross_income", label: "Monthly gross income (USD)", type: "text", required: true, evidence: true, docTypes: ["paystub", "income_verification"] },
  { id: "requested_accommodation", label: "Requested accommodation (describe)", type: "textarea", required: true, evidence: true, docTypes: ["provider_letter"] },
]

export function guessDocType(name: string): string {
  const s = name.toLowerCase()
  if (s.includes("paystub")) return "paystub"
  if (s.includes("lease")) return "lease"
  if (s.includes("utility")) return "utility_bill"
  if (s.includes("provider") || s.includes("doctor")) return "provider_letter"
  if (s.includes("landlord")) return "landlord_letter"
  if (s.includes("ledger")) return "rent_ledger"
  return "other"
}

export function labelConfidence(c: number): string {
  if (c >= 0.8) return "High"
  if (c >= 0.55) return "Medium"
  if (c > 0) return "Low"
  return "—"
}

export function parseMoney(v: string | undefined | null): number | null {
  if (v == null) return null
  const s = String(v).split(",").join("").split("$").join("").trim()
  if (!s) return null
  const n = Number(s)
  if (Number.isNaN(n)) return null
  return n
}
