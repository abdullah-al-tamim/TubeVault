import { test, expect } from "@playwright/test";

for (const archive of [true, false]) {
  test(`${archive ? "archive" : "queue"} fuzzy folder search and reviewed bulk removal`, async ({
    page,
  }) => {
    const jobs = [
      {
        id: "a",
        title: "First.mp4",
        playlist: "Camera",
        path: "D:/Trips/Kuakata/First.mp4",
        state: archive ? "COMPLETED" : "QUEUED",
        size: 100,
        progress: 0,
        sha256: "abc",
        history_hidden: false,
      },
      {
        id: "b",
        title: "Second.mp4",
        playlist: "Camera",
        path: "D:/Trips/Kuakata/Second.mp4",
        state: archive ? "COMPLETED" : "QUEUED",
        size: 100,
        progress: 0,
        sha256: "def",
        history_hidden: false,
      },
      {
        id: "c",
        title: "Other.mp4",
        playlist: "Camera",
        path: "D:/Dhaka/Other.mp4",
        state: archive ? "COMPLETED" : "QUEUED",
        size: 100,
        progress: 0,
        sha256: "ghi",
        history_hidden: false,
      },
    ];
    const snapshot = {
      jobs,
      watches: [],
      mappings: [],
      instances: [],
      events: [],
      imports: [],
      account: null,
      settings: { paused: true, concurrency: 1 },
    };
    await page.route("**/api/session", (r) =>
      r.fulfill({ json: { csrf: "test" } }),
    );
    await page.route("**/api/setup/status", (r) =>
      r.fulfill({ json: { completed: true } }),
    );
    await page.route("**/api/snapshot", (r) => r.fulfill({ json: snapshot }));
    await page.route("**/api/events", (r) =>
      r.fulfill({ contentType: "text/event-stream", body: "" }),
    );
    let requests = 0;
    let fail = false;
    await page.route(
      `**/api/${archive ? "history" : "queue"}/bulk`,
      async (r) => {
        requests++;
        const body = r.request().postDataJSON();
        expect(body.ids).toEqual(["a", "b"]);
        if (fail) {
          await r.fulfill({ status: 409, json: { detail: "Try again" } });
          return;
        }
        for (const job of jobs.filter((j) => body.ids.includes(j.id))) {
          if (archive) job.history_hidden = body.action === "remove";
          else job.state = "REMOVED";
        }
        await r.fulfill({
          json: { results: body.ids.map((id: string) => ({ id, ok: true })) },
        });
      },
    );
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "A home for every memory." }),
    ).toBeVisible();
    if (await page.getByRole("button", { name: "Open navigation" }).isVisible())
      await page.getByRole("button", { name: "Open navigation" }).click();
    await page
      .getByRole("button", {
        name: archive ? "Archive History" : "Upload Queue",
        exact: true,
      })
      .click();
    await page.getByText("Folders · All", { exact: true }).click();
    await page.getByRole("checkbox", { name: /D:\/Trips\/Kuakata/ }).check();
    const search = page.getByLabel(
      archive ? "Search archive history" : "Search queue",
    );
    await search.fill("Kuakta");
    await expect(page.getByText(/2 shown/)).toBeVisible();
    await expect(
      page.getByRole("checkbox", { name: "Select Other.mp4", exact: true }),
    ).toHaveCount(0);
    await page
      .getByRole("checkbox", { name: "Select First.mp4", exact: true })
      .check();
    await search.fill("Second");
    await expect(
      page.getByRole("button", { name: "Remove selected", exact: true }),
    ).toBeDisabled();
    await search.fill("Kuakta");
    await page
      .getByLabel(
        archive
          ? "Select all shown archive entries"
          : "Select all shown videos",
      )
      .check();
    page.once("dialog", (dialog) => dialog.dismiss());
    await page
      .getByRole("button", { name: "Remove selected", exact: true })
      .click();
    expect(requests).toBe(0);
    fail = true;
    page.once("dialog", (dialog) => dialog.accept());
    await page
      .getByRole("button", { name: "Remove selected", exact: true })
      .click();
    await expect(page.getByRole("status")).toHaveText("Try again");
    fail = false;
    page.once("dialog", (dialog) => dialog.accept());
    await page
      .getByRole("button", { name: "Remove selected", exact: true })
      .click();
    await expect(page.getByText(/0 shown/)).toBeVisible();
    await page
      .getByLabel(archive ? "Archive history filter" : "Queue status filter")
      .selectOption(archive ? "removed" : "REMOVED");
    await expect(page.getByText(/2 shown/)).toBeVisible();
    if (archive) {
      await page.getByLabel("Select all shown archive entries").check();
      await page
        .getByRole("button", { name: "Restore selected", exact: true })
        .click();
      await expect(page.getByText(/0 shown/)).toBeVisible();
      await page.getByLabel("Archive history filter").selectOption("history");
      await expect(page.getByText(/2 shown/)).toBeVisible();
    }
  });
}
