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


// ============================================================
// 14. combo card with 2 data_refs renders both lines
// ============================================================
test("14 — combo card renders both data_refs (DGS10 + BTC)", async ({
  page,
  request,
}) => {
  const card = await createCard(request, {
    type: "combo",
    title: "VE2E combo 10y+BTC",
    data_refs: [
      { source: "fred", kind: "macro", name: "DGS10" },
      { source: "binance", kind: "ohlcv", name: "BTCUSDT" },
    ],
    chart_spec: { overlays: [], subplots: [] },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.getByText("VE2E combo 10y+BTC").first().waitFor({ timeout: 15_000 });
  await page.waitForTimeout(7_000);
  const cardBox = page
    .getByText("VE2E combo 10y+BTC")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'rounded-lg')][1]");
  const out = shotPath("14_combo");
  await cardBox.screenshot({ path: out });
  const cs = await colorContentScore(out);
  expect(cs, "combo chart should render content").toBeGreaterThan(0.01);
  console.log(`14_combo color_score=${cs.toFixed(4)}, id=${card.id}`);
});


// ============================================================
// 15. chart with every subplot type renders 5-row figure
// ============================================================
test("15 — chart with rsi/atr/volume/yoy renders all subplots", async ({
  page,
  request,
}) => {
  const card = await createCard(request, {
    type: "chart",
    title: "VE2E all subplots",
    data_refs: [{ source: "binance", kind: "ohlcv", name: "BTCUSDT" }],
    chart_spec: {
      overlays: [],
      subplots: ["rsi", "atr", "volume", "yoy"],
    },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.getByText("VE2E all subplots").first().waitFor({ timeout: 15_000 });
  await page.waitForTimeout(7_000);
  const cardBox = page
    .getByText("VE2E all subplots")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'rounded-lg')][1]");
  const out = shotPath("15_all_subplots");
  await cardBox.screenshot({ path: out });
  const cs = await colorContentScore(out);
  expect(cs, "all-subplots chart should render").toBeGreaterThan(0.01);
  console.log(`15_all_subplots color_score=${cs.toFixed(4)}, id=${card.id}`);
});


// ============================================================
// 16. EMA overlays
// ============================================================
test("16 — chart with ema_12 + ema_26 overlays renders both", async ({
  page,
  request,
}) => {
  const card = await createCard(request, {
    type: "chart",
    title: "VE2E ema",
    data_refs: [{ source: "binance", kind: "ohlcv", name: "BTCUSDT" }],
    chart_spec: { overlays: ["ema_12", "ema_26"], subplots: [] },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.getByText("VE2E ema").first().waitFor({ timeout: 15_000 });
  await page.waitForTimeout(7_000);
  const cardBox = page
    .getByText("VE2E ema")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'rounded-lg')][1]");
  const out = shotPath("16_ema_overlays");
  await cardBox.screenshot({ path: out });
  const cs = await colorContentScore(out);
  expect(cs, "EMA chart should render").toBeGreaterThan(0.02);
  console.log(`16_ema_overlays color_score=${cs.toFixed(4)}, id=${card.id}`);
});


// ============================================================
// 17. macro line chart (FRED, no OHLCV columns)
// ============================================================
test("17 — FRED DGS10 renders as line chart (not candlestick)", async ({
  page,
  request,
}) => {
  const card = await createCard(request, {
    type: "chart",
    title: "VE2E DGS10 line",
    data_refs: [{ source: "fred", kind: "macro", name: "DGS10" }],
    chart_spec: { overlays: [], subplots: [] },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.getByText("VE2E DGS10 line").first().waitFor({ timeout: 15_000 });
  await page.waitForTimeout(7_000);
  const cardBox = page
    .getByText("VE2E DGS10 line")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'rounded-lg')][1]");
  const out = shotPath("17_macro_line");
  await cardBox.screenshot({ path: out });
  const cs = await colorContentScore(out);
  expect(cs, "macro line chart should render").toBeGreaterThan(0.005);
  console.log(`17_macro_line color_score=${cs.toFixed(4)}, id=${card.id}`);
});


// ============================================================
// 18. every annotation kind round-trip
// ============================================================
test("18 — all annotation kinds (hline, vline, trendline, rect) persist", async ({
  request,
}) => {
  const card = await createCard(request, {
    type: "chart",
    title: "VE2E annot kinds",
    data_refs: [{ source: "binance", kind: "ohlcv", name: "BTCUSDT" }],
    chart_spec: { overlays: [], subplots: [], annotations: [] },
  });
  const kinds: Array<{ kind: string; points: [number, number][]; label: string }> = [
    { kind: "hline", points: [[0, 70_000]], label: "support" },
    { kind: "vline", points: [[1_700_000_000, 0]], label: "event" },
    {
      kind: "trendline",
      points: [
        [1_700_000_000, 60_000],
        [1_730_000_000, 80_000],
      ],
      label: "uptrend",
    },
    {
      kind: "rect",
      points: [
        [1_700_000_000, 55_000],
        [1_730_000_000, 75_000],
      ],
      label: "consolidation",
    },
  ];
  for (const a of kinds) {
    const r = await request.post(`/api/cards/${card.id}/annotations`, {
      data: { annotation: a, target: "working" },
    });
    expect((await r.json()).ok).toBe(true);
  }
  const reloaded = (await (await request.get("/api/cards/working")).json()).find(
    (c: { id: string }) => c.id === card.id,
  );
  const labels = reloaded.chart_spec.annotations.map((a: { label: string }) => a.label);
  expect(new Set(labels)).toEqual(
    new Set(["support", "event", "uptrend", "consolidation"]),
  );
});


// ============================================================
// 19. detect_channels → channel_annotations workflow
//
// We exercise the tool surface directly (via /api/cards/{id}/annotations
// since channel_annotations is composed of trendline annotations) — the
// agent does the algorithmic detection step. Here we just verify a
// channel-shaped pair of trendlines renders on a chart.
// ============================================================
test("19 — detected channel renders as two trendlines on a chart", async ({
  page,
  request,
}) => {
  const card = await createCard(request, {
    type: "chart",
    title: "VE2E channel detection",
    data_refs: [{ source: "binance", kind: "ohlcv", name: "BTCUSDT" }],
    chart_spec: { overlays: [], subplots: [] },
  });
  const t0 = 1_700_000_000;
  const t1 = 1_730_000_000;
  for (const [lo, hi, label, color] of [
    [60_000, 90_000, "channel upper", "#ef4444"],
    [50_000, 80_000, "channel lower", "#22c55e"],
  ] as const) {
    await request.post(`/api/cards/${card.id}/annotations`, {
      data: {
        annotation: {
          kind: "trendline",
          points: [
            [t0, lo],
            [t1, hi],
          ],
          label,
          color,
        },
        target: "working",
      },
    });
  }
  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page
    .getByText("VE2E channel detection")
    .first()
    .waitFor({ timeout: 15_000 });
  await page.waitForTimeout(7_000);
  const cardBox = page
    .getByText("VE2E channel detection")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'rounded-lg')][1]");
  const out = shotPath("19_channel");
  await cardBox.screenshot({ path: out });
  const cs = await colorContentScore(out);
  expect(cs, "channel chart should render trendlines").toBeGreaterThan(0.01);
  console.log(`19_channel color_score=${cs.toFixed(4)}, id=${card.id}`);
});


// ============================================================
// 20. save-to-main button promotes a working card; main badge ticks up
// ============================================================
test("20 — save (★) button promotes working card to main", async ({
  page,
  request,
}) => {
  const card = await createCard(request, {
    type: "analysis",
    title: "VE2E save click",
    analysis_markdown: "promote me",
  });
  // Snapshot main count before
  const beforeMain = (await (await request.get("/api/cards/main")).json()).length;

  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.getByText("VE2E save click").first().waitFor();

  // Save button lives in the grid item action row; scope by card.
  const cardItem = page
    .getByText("VE2E save click")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'react-grid-item')][1]");
  await cardItem.locator('[data-testid="save-card"]').click();
  await page.waitForTimeout(2_000);

  const afterMain = (await (await request.get("/api/cards/main")).json()).length;
  expect(afterMain).toBe(beforeMain + 1);
  expect(
    (await (await request.get("/api/cards/main")).json()).some(
      (c: { id: string }) => c.id === card.id,
    ),
  ).toBe(true);
});


// ============================================================
// 21. delete (✕) button removes the card via UI
// ============================================================
test("21 — delete (✕) button removes a working card", async ({
  page,
  request,
}) => {
  const card = await createCard(request, {
    type: "analysis",
    title: "VE2E delete click",
    analysis_markdown: "remove me",
  });
  const before = (await (await request.get("/api/cards/working")).json()).length;

  // Auto-accept the JS confirm() prompt in handleDelete.
  page.on("dialog", (d) => d.accept());

  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.getByText("VE2E delete click").first().waitFor();

  const cardItem = page
    .getByText("VE2E delete click")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'react-grid-item')][1]");
  await cardItem.locator('[data-testid="delete-card"]').click();
  await page.waitForTimeout(2_000);

  const after = (await (await request.get("/api/cards/working")).json()).length;
  expect(after).toBe(before - 1);
  expect(
    (await (await request.get("/api/cards/working")).json()).some(
      (c: { id: string }) => c.id === card.id,
    ),
  ).toBe(false);
});


// ============================================================
// 22. Refresh-now button bumps the data epoch (force-refreshes /api/data)
// ============================================================
test("22 — Refresh button triggers a fresh /api/data fetch", async ({
  page,
  request,
}) => {
  await createCard(request, {
    type: "chart",
    title: "VE2E refresh target",
    data_refs: [{ source: "binance", kind: "ohlcv", name: "BTCUSDT" }],
    chart_spec: { overlays: [], subplots: [] },
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Working/i }).click();
  await page.getByText("VE2E refresh target").first().waitFor();
  await page.waitForTimeout(4_000);

  // Listen for /api/data requests AFTER initial render. Refresh should
  // trigger at least one request, and it should include refresh=true.
  const refreshRequests: string[] = [];
  page.on("request", (req) => {
    const url = req.url();
    if (url.includes("/api/data")) refreshRequests.push(url);
  });

  await page.locator('[data-testid="refresh-now"]').click();
  await page.waitForTimeout(4_000);

  expect(
    refreshRequests.some((u) => u.includes("refresh=true")),
    `expected a /api/data call with refresh=true; saw ${refreshRequests.length} call(s)`,
  ).toBe(true);
});
