import {test,expect} from '@playwright/test';
const snapshot={jobs:[],watches:[],mappings:[],instances:[],events:[],imports:[],account:null,settings:{paused:true,mode:'manual',concurrency:1}};
test('authenticated dashboard and responsive navigation',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{csrf:'test'}}));
 await page.route('**/api/snapshot',r=>r.fulfill({json:snapshot}));
 await page.route('**/api/events',r=>r.fulfill({contentType:'text/event-stream',body:`data: ${JSON.stringify(snapshot)}\n\n`}));
 await page.goto('/');await expect(page.getByRole('heading',{name:'A home for every memory.'})).toBeVisible();
 await expect(page.getByText('No compression. No source deletion.')).toBeAttached();
 if(await page.getByRole('button',{name:'Open navigation'}).isVisible())await page.getByRole('button',{name:'Open navigation'}).click();
 await page.getByRole('button',{name:'iPhone Imports',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Keep the original. Bring it home.'})).toBeVisible();
 await expect(page.getByLabel('Destination collection')).toBeVisible();
});
test('login errors are displayed',async({page})=>{await page.route('**/api/session',r=>r.fulfill({status:401,json:{detail:'Sign in required'}}));await page.route('**/api/login',r=>r.fulfill({status:401,json:{detail:'Invalid password'}}));await page.goto('/');await page.getByLabel('Vault password').fill('incorrect password');await page.getByRole('button',{name:'Unlock vault'}).click();await expect(page.getByRole('alert')).toHaveText('Invalid password');});
