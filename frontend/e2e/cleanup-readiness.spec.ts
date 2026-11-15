import { test, expect } from "@playwright/test";

test("delete prerequisites explain running queue and wait for active operations", async ({
  page,
}) => {
  let paused = false;
  let active = true;
  let deleted = 0;
  const snapshot = () => ({
    jobs: active
      ? [
          {
            id: "upload",
            title: "Active",
            state: "UPLOADING",
            claimed: true,
            size: 10,
            progress: 1,
          },
        ]
      : [],
    watches: [],
    mappings: [],
    events: [],
    instances: [],
    imports: [],
    settings: { paused },
  });
  await page.route("**/api/session", (r) =>
    r.fulfill({ json: { csrf: "test" } }),
  );
  await page.route("**/api/setup/status", (r) =>
    r.fulfill({ json: { completed: true } }),
  );
  await page.route("**/api/snapshot", (r) => r.fulfill({ json: snapshot() }));
  await page.route("**/api/events", (r) =>
    r.fulfill({ contentType: "text/event-stream", body: "" }),
  );
  await page.route("**/api/queue/pause", (r) => {
    paused = true;
    return r.fulfill({ json: { ok: true } });
  });
  await page.route("**/api/cleanup", (r) => {
    if (r.request().method() === "GET")
      return r.fulfill({
        json: [
          {
            id: "original",
            path: "Camera/clip.mp4",
            size: 4096,
            video_id: "abcdefghijk",
          },
        ],
      });
    deleted++;
    if (deleted === 1)
      return r.fulfill({ json: [{ id: "original", ok: false, reason: "quotaExceeded", can_use_saved: true }] });
    expect(r.request().postDataJSON()).toEqual({
      use_saved_verification: true,
      ids: ["original"],
      confirmation: "DELETE ORIGINALS",
    });
    return r.fulfill({ json: [{ id: "original", ok: true }] });
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
  await page
    .getByRole("button", { name: "Select all shown originals" })
    .click();
  const remove = page.getByRole("button", {
    name: "Permanently delete 1 original(s)",
    exact: true,
  });
  await expect(remove).toBeDisabled();
  await expect(remove).toHaveCSS("cursor", "not-allowed");
  await expect(remove).toHaveAttribute("aria-busy", "false");
  await expect(
    page.getByText("Pause the upload queue to enable permanent deletion.", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Pause queue to enable deletion",
      exact: true,
    })
    .click();
  await expect(
    page.getByText(/Waiting for 1 active upload operation/),
  ).toBeVisible();
  await expect(remove).toBeDisabled();
  expect(deleted).toBe(0);
  active = false;
  // A navigation reload obtains a fresh snapshot, as does a live SSE update.
  await page.reload();
  if (await page.getByRole("button", { name: "Open navigation" }).isVisible())
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "Archive History", exact: true })
    .click();
  await page.getByRole("button", { name: "Review uploaded originals" }).click();
  await page
    .getByRole("button", { name: "Select all shown originals" })
    .click();
  await expect(remove).toBeEnabled();
  page.once("dialog", d => d.accept());
  await remove.click();
  await expect(page.getByRole("status")).toContainText("quotaExceeded");
  const retry = page.getByRole("button", { name: "Delete using saved verification" });
  page.once("dialog", d => d.dismiss());
  await retry.click();
  expect(deleted).toBe(1);
  page.once("dialog", d => d.accept());
  await retry.click();
  await expect(page.getByRole("status")).toHaveText(
    "Deleted 1 local original(s).",
  );
  expect(deleted).toBe(2);
});
