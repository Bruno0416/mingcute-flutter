#!/usr/bin/env node
/**
 * Captures static PNG scenes from the Flutter Web preview (capture mode).
 *
 * Usage (invoked by tool/generate_screenshots.sh):
 *   node capture.mjs --url http://127.0.0.1:PORT/ --out DIR --results FILE [--only a,b]
 *   node capture.mjs ... --compare REFDIR      # pixel-compare instead of overwrite
 *
 * Readiness comes from the page itself (MINGCUTE_CAPTURE_READY console
 * message, printed after two rendered frames), never from a fixed sleep.
 */
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url));
const args = Object.fromEntries(process.argv.slice(2).flatMap((a, i, all) =>
  a.startsWith('--') ? [[a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : 'true']] : []));
const config = JSON.parse(await readFile(join(here, 'scenes.json'), 'utf8'));
const url = args.url ?? 'http://127.0.0.1:8765/';
const out = resolve(args.out ?? 'out');
const only = args.only ? args.only.split(',') : config.scenes.map((s) => s.name);
const unknown = only.filter((n) => !config.scenes.some((s) => s.name === n));
if (unknown.length) {
  console.error(`Unknown scene(s): ${unknown.join(', ')}. Valid: ${config.scenes.map((s) => s.name).join(', ')}`);
  process.exit(2);
}
const readyTimeout = 90000;

function compare(aBuf, bBuf) {
  const a = PNG.sync.read(aBuf);
  const b = PNG.sync.read(bBuf);
  if (a.width !== b.width || a.height !== b.height) {
    return { differing: -1, total: 0, note: `size ${a.width}x${a.height} vs ${b.width}x${b.height}` };
  }
  let differing = 0;
  let maxDelta = 0;
  for (let i = 0; i < a.data.length; i += 4) {
    let d = 0;
    for (let c = 0; c < 4; c++) d = Math.max(d, Math.abs(a.data[i + c] - b.data[i + c]));
    if (d > 0) differing++;
    if (d > maxDelta) maxDelta = d;
  }
  return { differing, total: a.width * a.height, maxDelta };
}

let browser;
let failed = false;
const results = [];
try {
  await mkdir(out, { recursive: true });
  browser = await chromium.launch({
    headless: true,
    ...(process.env.MINGCUTE_SCREENSHOT_BROWSER ? { executablePath: process.env.MINGCUTE_SCREENSHOT_BROWSER } : {}),
    args: ['--font-render-hinting=none', '--force-color-profile=srgb', '--disable-lcd-text',
      '--hide-scrollbars', '--enable-unsafe-swiftshader'],
  });
  for (const name of only) {
    const scene = config.scenes.find((s) => s.name === name);
    const context = await browser.newContext({
      viewport: config.viewport,
      deviceScaleFactor: config.deviceScaleFactor,
      reducedMotion: 'reduce',
      colorScheme: scene.params.theme === 'light' ? 'light' : 'dark',
      locale: 'en-US',
      timezoneId: 'UTC',
    });
    try {
      const page = await context.newPage();
      const target = new URL(url);
      for (const [k, v] of Object.entries(scene.params)) target.searchParams.set(k, v);
      let ready;
      let problem;
      const readyPromise = new Promise((res, rej) => { ready = res; problem = rej; });
      page.on('console', (m) => {
        const text = m.text();
        if (text.startsWith('MINGCUTE_CAPTURE_READY ')) ready(JSON.parse(text.slice(23)));
        else if (text.startsWith('MINGCUTE_CAPTURE_ERROR')) problem(new Error(text));
      });
      page.on('pageerror', (e) => problem(new Error(`page error: ${e.message}`)));
      await page.goto(target.href, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.locator('flutter-view').waitFor({ state: 'attached', timeout: 60000 });
      const timer = setTimeout(() => problem(new Error(`${name}: capture-ready signal timed out`)), readyTimeout);
      const info = await readyPromise.finally(() => clearTimeout(timer));
      if (info.scene !== scene.params.capture || info.theme !== (scene.params.theme ?? 'dark') || !(info.count > 0)) {
        throw new Error(`${name}: ready payload does not match scene: ${JSON.stringify(info)}`);
      }
      await page.addStyleTag({ content: '*{cursor:none!important;caret-color:transparent!important}' });
      await page.evaluate(() => document.fonts.ready);
      await page.mouse.move(config.viewport.width - 1, config.viewport.height - 1);
      await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
      const png = await page.screenshot({ type: 'png', animations: 'disabled', caret: 'hide' });
      const header = PNG.sync.read(png);
      const file = `${name}.png`;
      if (args.compare) {
        const ref = await readFile(join(resolve(args.compare), file)).catch(() => null);
        if (!ref) throw new Error(`${file}: reference image is missing`);
        const diff = compare(png, ref);
        console.log(`[pixels] ${name}: ${diff.differing} of ${diff.total} pixels differ (max channel delta ${diff.maxDelta ?? 'n/a'}) ${diff.note ?? ''}`);
        results.push({ name, file, ...diff, names: info.names });
        if (diff.differing !== 0) failed = true;
      } else {
        await writeFile(join(out, file), png);
        console.log(`[capture] ${name}: ${header.width}x${header.height}, ${png.length} bytes, ${info.count} icons`);
        results.push({ name, file, width: header.width, height: header.height, count: info.count, names: info.names });
      }
    } finally {
      await context.close();
    }
  }
} catch (error) {
  console.error(`[capture] FAILED: ${error.message}`);
  failed = true;
} finally {
  await browser?.close();
}
if (args.results) await writeFile(resolve(args.results), JSON.stringify({ results }, null, 2));
process.exit(failed ? 1 : 0);
