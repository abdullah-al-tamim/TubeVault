import {test, expect} from "@playwright/test";
import {readFile} from "node:fs/promises";
import {resolve} from "node:path";

test("phone page pairs and copies a selected video in chunks", async ({page})=>{
  for(const [url,file,type] of [["/","index.html","text/html"],["/phone.js","phone.js","text/javascript"],["/phone.css","phone.css","text/css"]]){
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
