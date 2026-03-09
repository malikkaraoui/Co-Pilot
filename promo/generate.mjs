import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const pages = [
  { name: 'screenshot-1280x800', file: 'screenshot.html', width: 1280, height: 800 },
  { name: 'small-promo-440x280', file: 'small-promo.html', width: 440, height: 280 },
  { name: 'large-promo-1400x560', file: 'large-promo.html', width: 1400, height: 560 },
];

async function main() {
  const browser = await chromium.launch({ headless: true });

  for (const p of pages) {
    console.log(`Generating ${p.name}...`);
    const context = await browser.newContext({
      viewport: { width: p.width, height: p.height },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    await page.goto(`http://localhost:8765/${p.file}`, { waitUntil: 'networkidle' });
    // Wait for fonts
    await page.waitForTimeout(1500);

    // Screenshot as JPEG (no alpha, as required by Chrome Web Store)
    await page.screenshot({
      path: path.join(__dirname, `${p.name}.jpg`),
      type: 'jpeg',
      quality: 95,
      fullPage: false,
    });

    // Also PNG 24-bit (flatten alpha by compositing on white)
    await page.screenshot({
      path: path.join(__dirname, `${p.name}.png`),
      type: 'png',
      fullPage: false,
    });

    await context.close();
    console.log(`  -> ${p.name}.jpg + .png`);
  }

  await browser.close();
  console.log('Done!');
}

main().catch(e => { console.error(e); process.exit(1); });
