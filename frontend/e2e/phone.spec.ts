import {test, expect} from "@playwright/test";
import {readFile} from "node:fs/promises";
import {resolve} from "node:path";
import {createHash} from "node:crypto";

const hash = (value: Buffer) => createHash("sha256").update(value).digest("hex");

test("phone page pairs and copies a selected video in chunks", async ({page})=>{
  for(const [url,file,type] of [["/","index.html","text/html"],["/phone.js","phone.js","text/javascript"],["/transfer-policy.js","transfer-policy.js","text/javascript"],["/phone.css","phone.css","text/css"]]){
    const body=await readFile(resolve("..","phone",file));
    await page.route("http://127.0.0.1:4173"+url,route=>route.fulfill({body,contentType:type}));
  }
  await page.route("**/pair",async route=>{
    expect(route.request().postDataJSON()).toEqual({invitation:"test-invitation"});
    await route.fulfill({json:{token:"phone-token"}});
  });
  await page.route("**/status",route=>route.fulfill({json:{collection:"iPhone memories",queue_paused:false}}));
  await page.route("**/connection-test",async route=>{
    expect(route.request().headers().authorization).toBe("Bearer phone-token");
    expect(route.request().postDataBuffer()?.length).toBe(1024*1024);
    await route.fulfill({json:{bytes:1024*1024,receive_seconds:.01}});
  });
  let offset=0;
  await page.route("**/files",async route=>{
    expect(route.request().headers().authorization).toBe("Bearer phone-token");
    expect(route.request().postDataJSON()).toEqual({filename:"phone.mov",size:12});
    await route.fulfill({json:{id:"transfer"}});
  });
  await page.route("**/files/transfer",route=>route.fulfill({json:{offset,state:"RECEIVING"}}));
  await page.route("**/files/transfer?offset=0",async route=>{
    expect(route.request().postDataBuffer()).toEqual(Buffer.from("originaldata"));
    offset=12;await route.fulfill({json:{offset}});
  });
  await page.route("**/files/transfer/finish",route=>route.fulfill({json:{saved:true}}));
  await page.goto("/#pair=test-invitation");
  await expect(page.getByText("Collection · iPhone memories")).toBeVisible();
  await expect(page).toHaveURL("http://127.0.0.1:4173/");
  await page.getByRole("button",{name:"Test connection",exact:true}).click();
  await expect(page.locator("#connection-result")).toContainText("Sample transfer is quick");
  await page.locator("#videos").setInputFiles({name:"phone.mov",mimeType:"video/quicktime",buffer:Buffer.from("originaldata")});
  await page.getByRole("button",{name:"Send to PC",exact:true}).click();
  await expect(page.getByText("Saved on PC · queued for YouTube")).toBeVisible();
  expect(offset).toBe(12);
});

for (const failure of ["before-save", "after-save", "response-stalled"]) {
  test(`phone recovers a chunk ${failure} without restarting the file`, async ({page}) => {
    for (const [url, file, type] of [["/", "index.html", "text/html"], ["/phone.js", "phone.js", "text/javascript"], ["/transfer-policy.js", "transfer-policy.js", "text/javascript"], ["/phone.css", "phone.css", "text/css"]]) {
      await page.route("http://127.0.0.1:4173" + url, async route => route.fulfill({
        body: await readFile(resolve("..", "phone", file)), contentType: type
      }));
    }
    await page.route("**/pair", route => route.fulfill({json: {token: "phone-token"}}));
    await page.route("**/status", route => route.fulfill({json: {collection: "Phone", queue_paused: true}}));
    await page.route("**/files", route => route.fulfill({json: {id: "transfer"}}));
    const original = Buffer.alloc(2600000);
    for (let i = 0; i < original.length; i++) original[i] = i % 251;
    let offset = 0;
    let puts = 0;
    const sizes: number[] = [];
    const committed: Buffer[] = [];
    await page.route("**/files/transfer", route => route.fulfill({json: {offset, state: "RECEIVING"}}));
    await page.route("**/files/transfer?offset=*", async route => {
      const start = Number(new URL(route.request().url()).searchParams.get("offset"));
      const body = route.request().postDataBuffer()!;
      expect(start).toBe(offset);
      expect(body.length).toBeLessThanOrEqual(4 * 1024 * 1024);
      sizes.push(body.length);
      expect(hash(body)).toBe(hash(original.subarray(start, start + body.length)));
      puts++;
      if (puts === 1) {
        if (failure !== "before-save") { offset += body.length; committed.push(body); }
        if (failure === "response-stalled") {
          // Polling must discover the commit and advance without waiting for this reply.
          await new Promise(resolve => setTimeout(resolve, 3000));
          await route.fulfill({json: {offset}}).catch(() => {}); return;
        }
        await route.abort("failed"); return;
      }
      offset += body.length; committed.push(body);
      await route.fulfill({json: {offset}});
    });
    await page.route("**/files/transfer/finish", route => route.fulfill({json: {saved: true}}));
    await page.goto("/#pair=test-invitation");
    await expect(page.locator("#sender")).toBeVisible();
    await page.locator("#videos").setInputFiles({name: "phone.mov", mimeType: "video/quicktime", buffer: original});
    await page.getByRole("button", {name: "Send to PC", exact: true}).click();
    await expect(page.getByText("Saved on PC · queued for YouTube")).toBeVisible();
    expect(hash(Buffer.concat(committed))).toBe(hash(original));
    if (failure !== "response-stalled") expect(sizes[1]).toBeLessThanOrEqual(sizes[0] / 2);
  });
}

test("phone grows transfer pieces on a fast connection and preserves exact bytes", async ({page}) => {
  for (const [url, file, type] of [["/", "index.html", "text/html"], ["/phone.js", "phone.js", "text/javascript"], ["/transfer-policy.js", "transfer-policy.js", "text/javascript"], ["/phone.css", "phone.css", "text/css"]]) {
    await page.route("http://127.0.0.1:4173" + url, async route => route.fulfill({body: await readFile(resolve("..", "phone", file)), contentType: type}));
  }
  await page.route("**/pair", route => route.fulfill({json: {token: "phone-token"}}));
  await page.route("**/status", route => route.fulfill({json: {collection: "Phone", queue_paused: true}}));
  await page.route("**/files", route => route.fulfill({json: {id: "transfer"}}));
  const original = Buffer.alloc(12 * 1024 * 1024, 37);
  let offset = 0;
  const sizes: number[] = [];
  await page.route("**/files/transfer", route => route.fulfill({json: {offset, state: "RECEIVING"}}));
  await page.route("**/files/transfer?offset=*", async route => {
    expect(Number(new URL(route.request().url()).searchParams.get("offset"))).toBe(offset);
    const body = route.request().postDataBuffer()!;
    expect(hash(body)).toBe(hash(original.subarray(offset, offset + body.length)));
    sizes.push(body.length); offset += body.length;
    await route.fulfill({json: {offset}});
  });
  await page.route("**/files/transfer/finish", route => route.fulfill({json: {saved: true}}));
  await page.goto("/#pair=test-invitation");
  await expect(page.locator("#sender")).toBeVisible();
  await page.locator("#videos").setInputFiles({name: "phone.mov", mimeType: "video/quicktime", buffer: original});
  await page.getByRole("button", {name: "Send to PC", exact: true}).click();
  await expect(page.getByText("Saved on PC · queued for YouTube")).toBeVisible({timeout: 15000});
  expect(sizes).toEqual([1, 1, 2, 2, 4, 2].map(n => n * 1024 * 1024));
  expect(offset).toBe(original.length);
});
