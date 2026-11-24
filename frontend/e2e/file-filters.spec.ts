import { test, expect } from "@playwright/test";

test("originals checklists filter live and clear hidden selections", async ({
  page,
}) => {
  const files = [
    {
      id: "a",
      path: "C:/Trips/Kuakata/arrival.mp4",
      size: 200_000_000,
      video_id: "abcdefghijk",
    },
    {
      id: "b",
      path: "C:/Trips/Kuakata/sunset.mov",
      size: 20_000_000,
      video_id: "abcdefghijk",
    },
    {
      id: "c",
      path: "C:/Trips/Dhaka/city.mp4",
      size: 20_000_000,
      video_id: "abcdefghijk",
    },
  ];
  await page.route("**/api/session", (r) =>
    r.fulfill({ json: { csrf: "test" } }),
  );
  await page.route("**/api/setup/status", (r) =>
    r.fulfill({ json: { completed: true } }),
  );
  await page.route("**/api/snapshot", (r) =>
    r.fulfill({
      json: {
        jobs: [],
        watches: [],
        mappings: [],
        events: [],
        instances: [],
        imports: [],
        settings: { paused: true },
      },
    }),
  );
  await page.route("**/api/events", (r) =>
    r.fulfill({ contentType: "text/event-stream", body: "" }),
  );
  await page.route("**/api/cleanup", async (r) => {
    if (r.request().method() === "GET") return r.fulfill({ json: files });
    expect(r.request().postDataJSON()).toEqual({
      ids: ["a"],
      confirmation: "DELETE ORIGINALS",
    });
    return r.fulfill({ json: [{ id: "a", ok: true }] });
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "A home for every memory." }),
  ).toBeVisible();
  if (await page.getByRole("button", { name: "Open navigation" }).isVisible())
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "Archive History", exact: true })
    .click();
  await page.getByRole("button", { name: "Review uploaded originals" }).click();
  const panel = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Free up space" }) });
  await panel.getByText("Folders · All", { exact: true }).click();
  await panel
    .getByRole("checkbox", { name: /^C:\/Trips\/Kuakata/ })
    .check();
  await expect(
    panel.getByText("2 of 3 files match", { exact: true }),
  ).toBeVisible();
  await panel
    .getByRole("button", { name: "Select all shown originals" })
    .click();
  await panel
    .getByLabel("Type DELETE ORIGINALS to confirm")
    .fill("DELETE ORIGINALS");
  await panel.getByText("File types · All", { exact: true }).click();
  await panel.getByRole("checkbox", { name: /^MP4/ }).check();
  await expect(
    panel.getByLabel("Type DELETE ORIGINALS to confirm"),
  ).toHaveValue("");
  await expect(
    panel.getByRole("button", {
      name: "Permanently delete 0 original(s)",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    panel.getByText("1 of 3 files match", { exact: true }),
  ).toBeVisible();
  await panel
    .getByRole("button", { name: "Select all shown originals" })
    .click();
  await panel
    .getByLabel("Type DELETE ORIGINALS to confirm")
    .fill("DELETE ORIGINALS");
  await panel
    .getByRole("button", {
      name: "Permanently delete 1 original(s)",
      exact: true,
    })
    .click();
  await panel
    .getByRole("button", { name: "Clear filters", exact: true })
    .click();
  await panel.getByLabel("Search uploaded originals").fill("zzzzzzzzzz");
  await expect(
    panel.getByText("No uploaded originals match these filters."),
  ).toBeVisible();
});
