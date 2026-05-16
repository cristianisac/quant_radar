/* eslint-disable @typescript-eslint/no-explicit-any */
import { mkdirSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

import { type APIRequestContext } from "@playwright/test";
import sharp from "sharp";

// ESM doesn't expose __dirname; derive it from import.meta.url.
const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const REPO_ROOT = path.resolve(__dirname, "../../../");
export const SHOTS_DIR = path.join(REPO_ROOT, "data", "visual_e2e");
mkdirSync(SHOTS_DIR, { recursive: true });

export const shotPath = (name: string) => path.join(SHOTS_DIR, `${name}.png`);

export async function pixelCoverage(filepath: string): Promise<number> {
  const { data, info } = await sharp(filepath)
    .raw()
    .toBuffer({ resolveWithObject: true });
  let lit = 0;
  const channels = info.channels;
  for (let i = 0; i < data.length; i += channels) {
    if (data[i] > 30 || data[i + 1] > 30 || data[i + 2] > 30) lit++;
  }
  return lit / (info.width * info.height);
}

// Stricter check for actual chart content: counts pixels whose channels
// vary noticeably from each other (e.g. green/red candlesticks, blue
// MA lines). A blank dark-grey panel scores ~0; a rendered chart with
// any colored traces scores well above 0.005. Catches "card frame
// rendered but Plotly is empty" bugs that ``pixelCoverage`` misses.
export async function colorContentScore(filepath: string): Promise<number> {
  const { data, info } = await sharp(filepath)
    .raw()
    .toBuffer({ resolveWithObject: true });
  let colored = 0;
  const channels = info.channels;
  for (let i = 0; i < data.length; i += channels) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    if (max - min > 40) colored++;
  }
  return colored / (info.width * info.height);
}

export async function resetState(request: APIRequestContext) {
  // Close + reopen working
  await request.post("/api/working/close").catch(() => undefined);
  await request.post("/api/working/new");
  // Wipe main
  const main = await (await request.get("/api/cards/main")).json();
  for (const c of main as any[]) {
    await request.delete(`/api/cards/${c.id}?target=main`);
  }
}

export async function createCard(
  request: APIRequestContext,
  body: Record<string, unknown>,
): Promise<any> {
  const r = await request.post("/api/cards", { data: body });
  if (!r.ok()) throw new Error(`POST /api/cards: ${r.status()} ${await r.text()}`);
  return r.json();
}
