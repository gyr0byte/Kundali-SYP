import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { chromium } from "playwright";

const origin = "http://127.0.0.1:3103";
const user = { id: "lunar-fixture", email: "moon-test@example.com", role: "user", language: "en",
  is_active: true, created_at: "2026-01-01T00:00:00Z" };
const profile = { id: "1252edf1-94cc-42f3-8caf-06fd6a4b8301", owner_id: user.id,
  label: "Moon window fixture", input_calendar: "BS", entered_date: "2072-01-12",
  date_ad: "2015-04-25", bs_conversion_status: "resolved", time_certainty: "unknown",
  time_local: null, place_name: "Kathmandu", latitude: 27.7, longitude: 85.3,
  timezone: "Asia/Kathmandu", created_at: user.created_at, updated_at: user.created_at };

for (const [locale, language, width, height] of [["en", "EN", 1440, 900], ["ne", "नेपाली", 375, 812]]) {
  test(`limited Moon presentation at ${width}px in ${locale}`, async () => {
    const { userWorkspace: labels } = JSON.parse(
      readFileSync(new URL(`../src/i18n/${locale}.json`, import.meta.url), "utf8")
    );
    const browser = await chromium.launch();
    try {
      const page = await browser.newPage({ viewport: { width, height }, locale });
      const exp = Math.floor(Date.now() / 1000) + 3600;
      const encode = (part) => Buffer.from(JSON.stringify(part)).toString("base64url");
      const token = `${encode({ alg: "HS256" })}.${encode({ sub: user.id, exp })}.sig`;
      await page.route("**/api/auth/refresh", route => route.fulfill({
        json: { authenticated: true, user, access_token: token, expires_at: exp * 1000 },
      }));
      const headers = {
        "access-control-allow-origin": origin,
        "access-control-allow-headers": "Authorization, Content-Type",
        "access-control-allow-methods": "GET, POST, OPTIONS",
      };
      await page.route("**/api/v1/profiles**", async route => {
        if (route.request().method() === "OPTIONS") return route.fulfill({status: 204, headers});
        if (route.request().method() === "GET") return route.fulfill({
          headers, json: { items: [profile], total: 1, limit: 50, offset: 0 },
        });
        assert.deepEqual(route.request().postDataJSON(), { ayanamsha: "lahiri" });
        return route.fulfill({
          headers,
          json: { profile_id: profile.id, profile_updated_at: profile.updated_at,
            input_calendar: "BS", time_certainty: "unknown",
            moon: { chart_id: "m_fixture", method: "moon-civil-window-v1", ayanamsha: "lahiri",
              utc_intervals: [], duration_seconds: 85500, ephemeris_source: "swieph",
              signs: { status: "stable", possible: [0] },
              nakshatras: { status: "uncertain", possible: ["Ashwini", "Bharani"] },
              padas: { status: "uncertain", possible: [{ nakshatra: "Ashwini", pada: 4 }, { nakshatra: "Bharani", pada: 1 }] },
            },
          },
        });
      });
      await page.goto(origin + "/user");
      await page.getByRole("button", {name: language, exact: true}).click();
      const panel = page.getByRole("region", {name: labels.moonWindow.title});
      await panel.getByText(labels.moonWindow.explanation).waitFor();
      await page.getByRole("button", {name: labels.moonWindow.calculate, exact: true}).click();
      await panel.getByText(labels.moonWindow.stable, {exact: true}).waitFor();
      await panel.getByText(labels.moonWindow.uncertain, {exact: true}).first().waitFor();
      await page.getByRole("region", {name: labels.dasha.title}).getByText(labels.dasha.unknown).waitFor();
      assert.match(await panel.textContent(), locale === "ne" ? /मेष/ : /Aries/);
      assert.equal(await page.getByRole("region", { name: labels.chartSectionTitle }).count(), 0);
      assert.equal(await page.getByRole("region", { name: labels.tableSectionTitle }).count(), 0);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    } finally {
      await browser.close();
    }
  });
}
