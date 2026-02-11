import type { FormField, MockDoc } from "./types"

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

export const sampleDocs: MockDoc[] = [
    {
        name: "Paystub_2026-01-15.pdf",
        docType: "paystub",
        status: "Ready",
        badge: "good",
        pages: 1,
        content: `ACME Logistics Inc.
123 Industrial Dr, Springfield, IL 62704

Pay Statement
Period: 01/01/2026 - 01/15/2026
Pay Date: 01/15/2026

Employee: Sarah Michelle Johnson
ID: EMP-9982

Earnings:
Regular Pay: 80 hrs @ $27.00/hr = $2,160.00
Overtime: 0 hrs
Gross Pay: $2,160.00

Taxes:
Federal w/h: $240.00
Medicare: $31.32
Social Security: $133.92
State IL: $108.00

Net Pay: $1,646.76

YTD Gross: $2,160.00`
    },
    {
        name: "Lease_Apt12.pdf",
        docType: "lease",
        status: "Ready",
        badge: "good",
        pages: 3,
        content: `RESIDENTIAL LEASE AGREEMENT

Landlord: Greenview Properties LLC
Tenant: Sarah Michelle Johnson

Premises: 12 Main St Apt 12, Springfield, IL 62701

Term: 12 months, beginning January 1, 2026 and ending December 31, 2026.

Rent: Tenant agrees to pay $1,650.00 per month, due on the 1st of each month.
Security Deposit: $1,650.00

Occupants: Tenant and 1 minor child (Household size: 2).

Landlord Contact:
Email: leasing@greenview.example
Phone: (555) 019-5555

Signatures:
[Signed] Sarah M. Johnson
[Signed] Greenview Prop.`
    },
    {
        name: "Utility_Bill_Jan.pdf",
        docType: "utility_bill",
        status: "Ready",
        badge: "good",
        pages: 1,
        content: `Springfield Power & Light
Service Address: 12 Main St Apt 12, Springfield, IL 62701
Account: 8827-112-99
Date: Jan 20, 2026

Customer: Sarah Michelle Johnson

Previous Balance: $0.00
Current Charges: $142.50
Total Due: $142.50 by Feb 10, 2026.`
    },
    {
        name: "Provider_Letter.pdf",
        docType: "provider_letter",
        status: "Ready",
        badge: "good",
        pages: 1,
        content: `Springfield Medical Group
Dr. Emily Chen, MD

To Whom It May Concern:

I am the treating physician for Sarah Johnson. She requires a reasonable accommodation for her housing due to a physical disability that limits her mobility. 

Specifically, Ms. Johnson requires a ground-floor unit or a unit with reliable elevator access, as she cannot safely navigate multiple flights of stairs.

Sincerely,
Dr. Emily Chen, MD
Feb 2, 2026`
    },
]

export const mockSuggestions: Record<string, {
    value: string
    confidence: number
    rationale: string
    citations: { doc: string; docType: string; page: string; chunk: string; quote: string }[]
    flags?: { code: string; severity: string; message: string }[]
    model: string
}> = {
    full_name: {
        value: "Jane Doe",
        confidence: 0.62,
        rationale: "Name appears on the lease header.",
        citations: [{ doc: "Lease_Apt12.pdf", docType: "lease", page: "1", chunk: "chk_00003", quote: "Tenant: Jane Doe" }],
        model: "claude-haiku (mock)"
    },
    dob: {
        value: "1990-05-02",
        confidence: 0.38,
        rationale: "DOB not clearly present in uploaded docs. Please confirm manually.",
        citations: [],
        flags: [{ code: "MISSING_EVIDENCE", severity: "warning", message: "DOB not found in documents." }],
        model: "claude-sonnet (mock)"
    },
    phone: {
        value: "+1 (555) 013-2207",
        confidence: 0.55,
        rationale: "Phone listed on applicant contact page in utility bill statement.",
        citations: [{ doc: "Utility_Bill_Jan.pdf", docType: "utility_bill", page: "1", chunk: "chk_00011", quote: "Contact: (555) 013-2207" }],
        model: "claude-haiku (mock)"
    },
    email: {
        value: "jane.doe@example.com",
        confidence: 0.45,
        rationale: "Email not reliably found; using user-provided default format.",
        citations: [],
        flags: [{ code: "LOW_CONFIDENCE", severity: "info", message: "Confirm email manually." }],
        model: "claude-sonnet (mock)"
    },
    address_line1: {
        value: "12 Main St Apt 12",
        confidence: 0.86,
        rationale: "Address appears on lease and utility bill; consistent across docs.",
        citations: [
            { doc: "Lease_Apt12.pdf", docType: "lease", page: "1", chunk: "chk_00002", quote: "Premises: 12 Main St Apt 12" },
            { doc: "Utility_Bill_Jan.pdf", docType: "utility_bill", page: "1", chunk: "chk_00010", quote: "Service Address: 12 Main St Apt 12" }
        ],
        model: "claude-sonnet (mock)"
    },
    city: {
        value: "Albany",
        confidence: 0.82,
        rationale: "City appears with address line on lease.",
        citations: [{ doc: "Lease_Apt12.pdf", docType: "lease", page: "1", chunk: "chk_00002", quote: "Albany, NY 12207" }],
        model: "claude-haiku (mock)"
    },
    state: {
        value: "NY",
        confidence: 0.92,
        rationale: "State code appears on lease and bill.",
        citations: [{ doc: "Lease_Apt12.pdf", docType: "lease", page: "1", chunk: "chk_00002", quote: "Albany, NY 12207" }],
        model: "claude-haiku (mock)"
    },
    zip: {
        value: "12207",
        confidence: 0.90,
        rationale: "ZIP appears on lease and bill.",
        citations: [{ doc: "Utility_Bill_Jan.pdf", docType: "utility_bill", page: "1", chunk: "chk_00010", quote: "Albany, NY 12207" }],
        model: "claude-haiku (mock)"
    },
    household_size: {
        value: "2",
        confidence: 0.40,
        rationale: "Household size not evidenced; set to 2 as a placeholder.",
        citations: [],
        flags: [{ code: "USER_CONFIRM", severity: "info", message: "Confirm household size manually." }],
        model: "claude-haiku (mock)"
    },
    landlord_name: {
        value: "Greenview Properties LLC",
        confidence: 0.78,
        rationale: "Landlord name found in lease signature section.",
        citations: [{ doc: "Lease_Apt12.pdf", docType: "lease", page: "3", chunk: "chk_00007", quote: "Landlord: Greenview Properties LLC" }],
        model: "claude-sonnet (mock)"
    },
    landlord_contact: {
        value: "leasing@greenview.example",
        confidence: 0.54,
        rationale: "Contact email extracted from lease footer; verify domain.",
        citations: [{ doc: "Lease_Apt12.pdf", docType: "lease", page: "3", chunk: "chk_00008", quote: "Contact: leasing@greenview.example" }],
        flags: [{ code: "DOMAIN_UNVERIFIED", severity: "warning", message: "Email domain may not resolve. Confirm contact." }],
        model: "claude-sonnet (mock)"
    },
    monthly_rent: {
        value: "$1,650",
        confidence: 0.70,
        rationale: "Monthly rent stated in lease; ensure it matches most recent ledger if available.",
        citations: [{ doc: "Lease_Apt12.pdf", docType: "lease", page: "2", chunk: "chk_00005", quote: "Monthly Rent: $1,650.00" }],
        model: "claude-sonnet (mock)"
    },
    employer_name: {
        value: "ACME Logistics",
        confidence: 0.68,
        rationale: "Employer name appears on most recent paystub header.",
        citations: [{ doc: "Paystub_2026-01-15.pdf", docType: "paystub", page: "1", chunk: "chk_00021", quote: "Employer: ACME Logistics" }],
        model: "claude-haiku (mock)"
    },
    monthly_gross_income: {
        value: "$4,320",
        confidence: 0.76,
        rationale: "Gross pay on biweekly stub ($2,160) × 2.0–2.2 ≈ monthly estimate. Confirm pay frequency.",
        citations: [{ doc: "Paystub_2026-01-15.pdf", docType: "paystub", page: "1", chunk: "chk_00022", quote: "Gross Pay: 2160.00 | Pay Period: 01/01 - 01/15" }],
        flags: [{ code: "ESTIMATED", severity: "info", message: "Monthly income is derived from pay frequency." }],
        model: "claude-sonnet (mock)"
    },
    requested_accommodation: {
        value: "Request transfer to an accessible, ground-floor unit (or elevator access) due to a mobility-related limitation that makes stair use unsafe.",
        confidence: 0.74,
        rationale: "Provider letter supports mobility limitation and need for stair-free access.",
        citations: [{ doc: "Provider_Letter.pdf", docType: "provider_letter", page: "1", chunk: "chk_00031", quote: "Patient requires stair-free access due to mobility impairment." }],
        model: "claude-opus (mock)"
    }
}

export function guessDocType(name: string): string {
    const s = name.toLowerCase()
    if (s.includes("paystub")) return "paystub"
    if (s.includes("lease")) return "lease"
    if (s.includes("utility")) return "utility_bill"
    if (s.includes("provider") || s.includes("doctor")) return "provider_letter"
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
