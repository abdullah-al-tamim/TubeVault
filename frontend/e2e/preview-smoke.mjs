import { chromium } from 'playwright';
const browser = await chromium.launch();
try {
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  await page.goto('http://127.0.0.1:8770');
  await page.getByRole('status').filter({hasText:'Sample data only'}).waitFor();
  await page.getByRole('heading',{name:'A home for every memory.'}).waitFor();
  await page.getByText('DJI_0001.mp4',{exact:true}).waitFor();
  await page.screenshot({path:'../data/screenshots/preview-overview.png',fullPage:true});
  await page.getByRole('button',{name:'Upload Queue',exact:false}).first().click();
  await page.getByText('Sample network interruption',{exact:true}).waitFor();
  await page.getByRole('button',{name:'iPhone Imports',exact:true}).click();
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('heading',{name:'Keep the original. Bring it home.'}).waitFor();
  await page.screenshot({path:'../data/screenshots/preview-mobile.png',fullPage:true});
  console.log('Preview smoke passed: sample banner, seeded videos, queue, and mobile import layout.');
} finally {await browser.close();}
