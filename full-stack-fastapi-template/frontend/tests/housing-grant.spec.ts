import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

test("Housing Grant happy path: upload, suggest, audit, save", async ({ page }) => {
  const documentId = "11111111-1111-1111-1111-111111111111"
  let listDocumentsCalls = 0

  await page.addInitScript(() => {
    localStorage.setItem("access_token", "test-token")
  })

  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        email: "housing@test.local",
        full_name: "Housing Tester",
        is_active: true,
        is_superuser: false,
      }),
    })
  })

  await page.route("**/api/v1/housing-grant/documents/upload-url", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        document_id: documentId,
        object_key: "housing-grant/users/u/documents/d/lease.txt",
        upload_url: `${route.request().url().split("/api/")[0]}/mock-upload/lease.txt`,
        required_headers: { "Content-Type": "text/plain" },
        expires_at: "2030-01-01T00:00:00Z",
      }),
    })
  })

  await page.route("**/mock-upload/**", async (route) => {
    await route.fulfill({
      status: 200,
      headers: { ETag: '"mock-etag-1"' },
      body: "",
    })
  })

  await page.route("**/api/v1/housing-grant/documents/*/complete", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ document_id: documentId, status: "uploaded" }),
    })
  })

  await page.route("**/api/v1/housing-grant/documents", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue()
      return
    }

    listDocumentsCalls += 1
    const data =
      listDocumentsCalls >= 2
        ? [
            {
              id: documentId,
              filename: "lease.txt",
              doc_type: "lease",
              status: "ready",
              pages: 1,
              badge: "good",
              created_at: "2030-01-01T00:00:00Z",
              updated_at: "2030-01-01T00:00:00Z",
            },
          ]
        : []

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data, count: data.length }),
    })
  })

  await page.route("**/api/v1/housing-grant/suggest-all", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        suggestions: [
          {
            field_id: "full_name",
            suggested_value: "Jane Applicant",
            confidence: 0.92,
            confidenceLabel: "High",
            rationale: "Name is present in uploaded lease.",
            citations: [
              {
                docId: documentId,
                doc: "lease.txt",
                docType: "lease",
                page: "1",
                chunk: "chk_00001",
                quote: "Tenant: Jane Applicant",
              },
            ],
            flags: [],
            model: "mock-model",
            usage: { input_tokens: 10, output_tokens: 5 },
          },
        ],
      }),
    })
  })

  await page.route("**/api/v1/housing-grant/preview-audit", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        flags: [
          {
            severity: "WARNING",
            code: "MISSING_EVIDENCE_REQUIRED",
            field_id: "monthly_rent",
            message: "Monthly rent has no linked evidence citation.",
            fix: "Run Suggest again.",
          },
        ],
        blockers: 0,
        warnings: 1,
        infos: 0,
        risk: 10,
        coveragePct: 20,
      }),
    })
  })

  await page.route("**/api/v1/housing-grant/submissions", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        submission_id: "22222222-2222-2222-2222-222222222222",
        audit_report_id: "33333333-3333-3333-3333-333333333333",
        status: "submitted",
      }),
    })
  })

  await page.goto("/housing-grant")

  await expect(page.getByText("Form AI Copilot")).toBeVisible()

  await page.setInputFiles("#fileInput", {
    name: "lease.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Tenant: Jane Applicant\nMonthly rent: 1200\n", "utf-8"),
  })

  await expect(page.getByText("lease.txt")).toBeVisible()
  await expect(page.getByText("ready", { exact: true })).toBeVisible()

  await page.getByRole("button", { name: "Suggest all" }).click()
  await expect(page.locator("#in_full_name")).toHaveValue("Jane Applicant")
  await expect(page.getByText("Tenant: Jane Applicant")).toBeVisible()

  await page.getByRole("button", { name: "Preview Audit" }).click()
  await expect(page.getByText("Review warnings")).toBeVisible()
  await page.getByRole("button", { name: "Warnings" }).click()
  await expect(page.getByText("MISSING_EVIDENCE_REQUIRED")).toBeVisible()

  await page.getByRole("button", { name: "Save submission" }).click()
  await expect(page.getByText("Submission saved")).toBeVisible()
})
