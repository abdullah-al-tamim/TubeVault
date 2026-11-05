import { chromium } from "playwright";
import { readFile, mkdir } from "node:fs/promises";
const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("http://127.0.0.1:8766");
  await page
    .getByLabel("Vault password")
    .fill((await readFile("../data/smoke/password.txt", "utf8")).trim());
  await page.getByRole("button", { name: "Unlock vault" }).click();
  await page
    .getByRole("heading", { name: "A home for every memory." })
    .waitFor();
  await mkdir("../data/screenshots", { recursive: true });
  await page.screenshot({
    path: "../data/screenshots/overview.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "iPhone Imports", exact: true })
    .click();
  await page.getByLabel("Destination collection").fill("Browser smoke test");
  const payload = Buffer.concat([
    Buffer.from([0, 0, 0, 24]),
    Buffer.from("ftypmp42"),
    Buffer.alloc(100000, 42),
  ]);
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "smoke-original.mp4",
      mimeType: "video/mp4",
      buffer: payload,
    });
  await page
    .getByText("ingested", { exact: true })
    .first()
    .waitFor({ timeout: 15000 });
  const snapshot = await page.evaluate(
    async () => await (await fetch("/api/snapshot")).json(),
  );
  if (!snapshot.imports.some((t) => t.state === "INGESTED"))
    throw new Error("Import not persisted");
  const imported = snapshot.imports.find((t) => t.state === "INGESTED");
  if (!(await readFile(imported.destination)).equals(payload))
    throw new Error("Imported bytes differ");
  if (!snapshot.settings.paused) throw new Error("Queue must remain paused");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../data/screenshots/mobile-import.png",
    fullPage: true,
  });
  if (errors.length) throw new Error(errors.join("\n"));
  console.log(
    "Real backend smoke passed: sign-in, SSE dashboard, byte-preserving import and paused queue.",
  );
} finally {
  await browser.close();
}
