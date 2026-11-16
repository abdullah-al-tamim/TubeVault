import { expect, test } from "@playwright/test";

test("pull an audio track after choosing a video cap", async ({ page }) => {
  const url = "https://youtu.be/abcdefghijk";
  let ready = false;
  const result = { id: "pull", video_id: "abcdefghijk", format: "mp3", state: "Ready", path: "C:/pulls/clip.mp3" };
  await page.route("**/api/session", r => r.fulfill({ json: { csrf: "test" } }));
  await page.route("**/api/setup/status", r => r.fulfill({ json: { completed: true } }));
  await page.route("**/api/events", r => r.fulfill({ contentType: "text/event-stream", body: "" }));
  await page.route("**/api/snapshot", r => r.fulfill({ json: {
    jobs: [], watches: [], mappings: [], instances: [], events: [], imports: [], settings: { paused: true }
  } }));
  await page.route("**/api/pulls", r => {
    if (r.request().method() === "POST") {
      expect(r.request().postDataJSON()).toEqual({ url, format: "mp3", height: null });
      ready = true;
      return r.fulfill({ status: 202, json: result });
    }
    return r.fulfill({ json: ready ? [result] : [] });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "A home for every memory." })).toBeVisible();
  const menu = page.getByRole("button", { name: "Open navigation" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("button", { name: "Video Pull" }).click();
  await page.getByLabel("YouTube link").fill(url);
  await page.getByLabel("Maximum video height").selectOption("1080");
  await page.getByLabel("Format", {exact: true}).selectOption("mp3");
  await expect(page.getByLabel("Maximum video height")).toHaveCount(0);
  await page.getByRole("button", { name: "Pull media" }).click();
  await expect(page.getByRole("link", { name: "Download file" })).toHaveAttribute("href", "/api/pulls/pull/file");
});
