/* Comprehensive end-to-end check:
 *  - hits every backend route at least once (1:1 with the tool surface)
 *  - renders every card type in a real browser
 *  - screenshots saved under data/visual_e2e/
 *  - blank-pixel coverage assertion guards against silent rendering bugs
 */

import { expect, test } from "@playwright/test";

import {
  colorContentScore,
  createCard,
  resetState,
  SHOTS_DIR,
  shotPath,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ request }) => {
  console.log(`screenshots → ${SHOTS_DIR}`);
  await resetState(request);
});

// ============================================================
// 1. Health + sources catalog
// ============================================================
test("01 — /api/health + /api/sources catalog completeness", async ({ request }) => {
  const h = await (await request.get("/api/health")).json();
  expect(h.status).toBe("ok");
  expect(h.version).toBeTruthy();

  const srcs = await (await request.get("/api/sources")).json();
  const names = new Set(srcs.map((s: { name: string }) => s.name));
  for (const expected of [
    "yfinance", "binance", "fred", "gdelt", "finnhub", "coinpaprika",
  ]) {
    expect(names).toContain(expected);
  }
});

// ============================================================
// 2. describe_source: known + 404
// ============================================================
test("02 — /api/sources/{name}: known 200 + unknown 404", async ({ request }) => {
  const r1 = await request.get("/api/sources/binance");
  expect(r1.status()).toBe(200);
  const known = await r1.json();
  expect(known.name).toBe("binance");

  const r2 = await request.get("/api/sources/nope");
  expect(r2.status()).toBe(404);
});

// ============================================================
// 3. probe-history live (yfinance + binance + fred)
// ============================================================
test("03 — probe-history hits 3 sources live", async ({ request }) => {
  for (const [symbol, source] of [
    ["AAPL", "yfinance"],
    ["BTC", "binance"],
  ]) {
    const r = await request.get(
      `/api/probe-history?symbol=${symbol}&source=${source}&kind=ohlcv`,
    );
    expect(r.status()).toBe(200);
    const out = await r.json();
    expect(out.bars).toBeGreaterThan(250);
  }
  const r = await request.get(
    "/api/probe-history?symbol=DGS10&source=fred&kind=macro",
  );
  expect(r.status()).toBe(200);
  const out = await r.json();
  expect(out.bars).toBeGreaterThan(250);
});

// ============================================================
// 4. /api/data live columnar
// ============================================================
test("04 — /api/data: columnar JSON for AAPL", async ({ request }) => {
  const r = await request.get(
    "/api/data?source=yfinance&kind=ohlcv&name=AAPL&interval=1d",
  );
  expect(r.status()).toBe(200);
  const d = await r.json();
  expect(d.timestamps.length).toBeGreaterThan(250);
  expect(d.columns.close).toBeTruthy();
});

// ============================================================
// 5. Chart card with overlays + subplots — visual
// ============================================================
test("05 — chart card with sma_50/200 + yoy renders non-blank", async ({
  page,
  request,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`PAGEERROR: ${err.message}`));
  page.on("requestfailed", (req) =>
    consoleErrors.push(`REQ_FAIL: ${req.url()} ${req.failure()?.errorText}`),
  );

  const card = await createCard(request, {
    type: "chart",
    title: "VE2E BTC overlays",
    data_refs: [{ source: "binance", kind: "ohlcv", name: "BTCUSDT" }],
    chart_spec: { overlays: ["sma_50", "sma_200"], subplots: ["yoy"] },
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.getByText("VE2E BTC overlays").first().waitFor({ timeout: 15_000 });
  // Plotly draws ~1s after fetch + mount; allow extra slack
  await page.waitForTimeout(6_000);

  const cardTitle = page.getByText("VE2E BTC overlays").first();
  await expect(cardTitle).toBeVisible();
  const cardBox = cardTitle.locator(
    "xpath=ancestor::*[contains(@class,'rounded-lg')][1]",
  );
  const out = shotPath("05_chart_overlays");
  await cardBox.screenshot({ path: out });
  const colorScore = await colorContentScore(out);

  if (consoleErrors.length) console.log("console errors:", consoleErrors);
  expect(consoleErrors, "no console errors in the page").toHaveLength(0);
  expect(
    colorScore,
    "chart card should contain colored chart pixels (not just dark panel)",
  ).toBeGreaterThan(0.02);
  console.log(`05_chart_overlays color_score=${colorScore.toFixed(4)}, id=${card.id}`);
});

// ============================================================
// 6. News card — DOM content
// ============================================================
test("06 — news card renders headlines", async ({ page, request }) => {
  await createCard(request, {
    type: "news",
    title: "VE2E news",
    news: [
      {
        title: "Fed signals rate cut",
        url: "https://example.com/a",
        source: "reuters.com",
        published_at: "2026-05-15T12:00:00Z",
      },
      {
        title: "AI stocks rally",
        url: "https://example.com/b",
        source: "bloomberg.com",
        published_at: "2026-05-15T13:00:00Z",
      },
    ],
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.waitForTimeout(2_000);
  await expect(page.getByText("Fed signals rate cut")).toBeVisible();
  await expect(page.getByText("AI stocks rally")).toBeVisible();
  await page.screenshot({ path: shotPath("06_news_card"), fullPage: true });
});

// ============================================================
// 7. Analysis card — markdown body
// ============================================================
test("07 — analysis card renders body", async ({ page, request }) => {
  await createCard(request, {
    type: "analysis",
    title: "VE2E analysis",
    analysis_markdown: "BTC is above its 50d MA and below its 200d MA.",
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.waitForTimeout(2_000);
  await expect(
    page.getByText("BTC is above its 50d MA and below its 200d MA."),
  ).toBeVisible();
});

// ============================================================
// 8. Sentiment card — body
// ============================================================
test("08 — sentiment card renders summary", async ({ page, request }) => {
  await createCard(request, {
    type: "sentiment",
    title: "VE2E sentiment",
    analysis_markdown: "Overall bullish across the headlines.",
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.waitForTimeout(2_000);
  await expect(
    page.getByText("Overall bullish across the headlines."),
  ).toBeVisible();
});

// ============================================================
// 9. PATCH /api/cards: update keeps id, applies title change
// ============================================================
test("09 — PATCH updates title in place; 404 for missing", async ({
  page,
  request,
}) => {
  const card = await createCard(request, {
    type: "analysis",
    title: "before",
    analysis_markdown: "x",
  });
  const r = await request.patch(`/api/cards/${card.id}`, {
    data: { title: "AFTER" },
  });
  expect(r.status()).toBe(200);

  const r404 = await request.patch(
    "/api/cards/00000000-0000-0000-0000-000000000000",
    { data: { title: "x" } },
  );
  expect(r404.status()).toBe(404);

  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.waitForTimeout(2_000);
  await expect(page.getByText("AFTER")).toBeVisible();
});

// ============================================================
// 10. save-to-main + tab badge updates
// ============================================================
test("10 — save-to-main increments Main tab badge", async ({ page, request }) => {
  const card = await createCard(request, {
    type: "analysis",
    title: "VE2E save target",
    analysis_markdown: "to persist",
  });
  const mainBefore = (await (await request.get("/api/cards/main")).json()).length;
  const r = await request.post(`/api/cards/${card.id}/save-to-main`);
  expect(r.status()).toBe(200);
  expect((await r.json()).ok).toBe(true);
  const mainAfter = (await (await request.get("/api/cards/main")).json()).length;
  expect(mainAfter).toBe(mainBefore + 1);

  await page.goto("/");
  await page.waitForTimeout(2_000);
  await expect(page.getByRole("button", { name: /Main \(/ })).toBeVisible();
});

// ============================================================
// 11. add_annotation persists; reload shows it
// ============================================================
test("11 — add_annotation persists and survives reload", async ({ request }) => {
  const card = await createCard(request, {
    type: "chart",
    title: "VE2E annotated",
    data_refs: [{ source: "binance", kind: "ohlcv", name: "BTCUSDT" }],
    chart_spec: { overlays: [], subplots: [], annotations: [] },
  });
  const r = await request.post(`/api/cards/${card.id}/annotations`, {
    data: {
      annotation: {
        kind: "hline",
        points: [[0.0, 70_000.0]],
        label: "support",
      },
      target: "working",
    },
  });
  expect((await r.json()).ok).toBe(true);

  const reloaded = (await (await request.get("/api/cards/working")).json()).find(
    (c: { id: string }) => c.id === card.id,
  );
  expect(reloaded.chart_spec.annotations.length).toBe(1);
  expect(reloaded.chart_spec.annotations[0].label).toBe("support");
});

// ============================================================
// 12. enlarge modal opens with draw tools
// ============================================================
test("12 — enlarge a chart card opens modal with draw tools", async ({
  page,
  request,
}) => {
  const card = await createCard(request, {
    type: "chart",
    title: "VE2E enlarge",
    data_refs: [{ source: "binance", kind: "ohlcv", name: "BTCUSDT" }],
    chart_spec: { overlays: ["sma_50"], subplots: [] },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.getByText("VE2E enlarge").first().waitFor();
  // Enlarge button is a sibling of the rounded-lg card body inside the
  // react-grid-item wrapper, not a descendant. Scope to the grid item.
  const cardTitle = page.getByText("VE2E enlarge").first();
  const gridItem = cardTitle.locator(
    "xpath=ancestor::*[contains(@class,'react-grid-item')][1]",
  );
  await gridItem.locator('button[title="Enlarge"]').click();
  // Modal heading is an <h2>; cards render their titles as <h3>.
  await expect(page.locator('h2', { hasText: "VE2E enlarge" })).toBeVisible();
  await page.waitForTimeout(2_500);
  await page.screenshot({ path: shotPath("12_enlarge_modal") });
  const colorScore = await colorContentScore(shotPath("12_enlarge_modal"));
  expect(
    colorScore,
    "enlarged chart should contain colored pixels (candles + lines)",
  ).toBeGreaterThan(0.005);
  console.log(`12 enlarge color_score=${colorScore.toFixed(4)}, id=${card.id}`);
});

// ============================================================
// 13. working lifecycle close → tab disappears
// ============================================================
test("13 — working lifecycle: close removes the Working tab", async ({
  page,
  request,
}) => {
  // Make sure working has at least one card so the tab is visible first
  await createCard(request, {
    type: "analysis", title: "tab marker", analysis_markdown: "_",
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Working/ })).toBeVisible();
  await request.post("/api/working/close");
  await page.waitForTimeout(6_000); // poll interval is 5s
  await page.reload();
  await expect(page.getByRole("button", { name: /Working/ })).toHaveCount(0);

  const state = await (await request.get("/api/working/state")).json();
  expect(state.is_open).toBe(false);
});
