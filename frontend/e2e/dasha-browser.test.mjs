import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";
import { chromium } from "playwright";

const origin = "http://127.0.0.1:3103";
const user = { id: "dasha-browser", email: "dasha-browser@example.com", role: "user", language: "en",
  is_active: true, created_at: "2026-01-01T00:00:00Z" };
const profile = { id: "2e9269c9-cba8-43eb-9cb7-4ec55964c081", owner_id: user.id,
  label: "Dasha fixture", input_calendar: "AD", entered_date: "2015-04-25", date_ad: "2015-04-25",
  time_certainty: "approximate", time_local: "13:01:09", latitude: 0, longitude: 0,
  place_name: "Synthetic", timezone: "Etc/UTC", created_at: user.created_at, updated_at: user.created_at };
const snapshot = "2b97cfa1-a291-45b4-a72d-2f8076067440";
const start = "2010-01-01T00:00:00.012345+00:00";
const birth = "2015-04-25T13:01:09.012345+00:00";
const transition = "2030-01-01T00:00:00.012345+00:00";
const end = "2130-01-01T00:00:00.012345+00:00";

function range(period_id, level, lord, start_utc, end_utc_exclusive, children = []) {
  return { period_id, level, lord, start_utc, end_utc_exclusive, children };
}
const pd = range("pd", "PD", "Mars", start, transition);
const ad = range("ad", "AD", "Sun", start, transition, [pd]);
const md = range("md", "MD", "Venus", start, transition, [ad]);
const laterLords = ["Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury", "Ketu"];
const later = laterLords.map((lord, index) => range(
  `md-${index + 2}`, "MD", lord,
  `${2030 + index * 13}-01-01T00:00:00.012345+00:00`,
  index === laterLords.length - 1 ? end : `${2043 + index * 13}-01-01T00:00:00.012345+00:00`,
));

for (const [locale, language, width, height] of [["en", "EN", 1440, 900], ["ne", "नेपाली", 375, 812]]) {
  test(`snapshot Dasha drill-down and stale lookup at ${width}px in ${locale}`, async () => {
    const { userWorkspace: labels } = JSON.parse(
      readFileSync(new URL(`../src/i18n/${locale}.json`, import.meta.url), "utf8")
    );
    const browser = await chromium.launch();
    try {
      const page = await browser.newPage({ viewport: { width, height }, locale, hasTouch: locale === "ne" });
      page.setDefaultTimeout(10_000);
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      const exp = Math.floor(Date.now() / 1000) + 3600;
      const encode = (part) => Buffer.from(JSON.stringify(part)).toString("base64url");
      const token = `${encode({ alg: "HS256" })}.${encode({ sub: user.id, exp })}.sig`;
      const headers = {
        "access-control-allow-origin": origin,
        "access-control-allow-headers": "Authorization, Content-Type",
        "access-control-allow-methods": "GET, POST, PATCH, OPTIONS",
        "access-control-expose-headers": "Location",
      };
      const settings = { ayanamsha: "lahiri", node_type: "mean", house_system: "whole_sign", year_days: 365.25, preset: null };
      await page.route("**/api/auth/refresh", route => route.fulfill({
        json: { authenticated: true, user, access_token: token, expires_at: exp * 1000 },
      }));
      let savedProfile = { ...profile };
      await page.route("**/api/v1/profiles**", async route => {
        const method = route.request().method();
        if (method === "OPTIONS") return route.fulfill({ status: 204, headers });
        if (method === "GET") return route.fulfill({
          headers, json: { items: [savedProfile], total: 1, limit: 50, offset: 0 },
        });
        if (method === "PATCH") {
          savedProfile = { ...savedProfile, ...route.request().postDataJSON(), updated_at: "2026-01-02T00:00:00Z" };
          return route.fulfill({ headers, json: savedProfile });
        }
        return route.fulfill({
          headers: { ...headers, Location: `/api/v1/charts/${snapshot}` },
          json: { profile_id: profile.id, profile_updated_at: savedProfile.updated_at,
            input_calendar: "AD", time_certainty: "approximate",
            chart: { chart_id: "c_fixture", engine_version: "0.2.0", settings, facts: [],
              metadata: { datetime_utc_iso: birth, ephemeris_source: "swieph" } },
          },
        });
      });
      let releaseOld;
      const blocked = new Promise(resolveOld => { releaseOld = resolveOld; });
      let sawOld;
      const oldStarted = new Promise(mark => { sawOld = mark; });
      let finishOld;
      const oldFinished = new Promise(mark => { finishOld = mark; });
      let requests = 0;
      await page.route(`**/api/v1/charts/${snapshot}/dasha?*`, async route => {
        if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
        const instant = new URL(route.request().url()).searchParams.get("as_of");
        requests++;
        if (requests === 1) return route.fulfill({ status: 500, headers, json: {} });
        const isOld = instant === "2010-01-01T00:00:00Z";
        if (isOld) {
          sawOld();
          await blocked;
        }
        const outside = instant === "2131-01-01T00:00:00Z";
        await route.fulfill({ headers, json: {
          snapshot_id: snapshot, chart_id: "c_fixture", timeline_id: "vd_fixture",
          method: "vimshottari-v1", time_certainty: "approximate", is_conditional: true,
          year_days: 365.25, profile_revision: 1, is_current_profile_revision: false,
          birth_utc: birth, start_utc: start, end_utc_exclusive: end,
          initial_balance: { nakshatra: "Bharani", lord: "Venus", remaining_years: { numerator: 4, denominator: 3 } },
          mahadashas: [md, ...later],
          lookup: {
            as_of: new Date(instant).toISOString().replace("Z", "000+00:00"),
            status: isOld ? "before_birth" : outside ? "outside_cycle" : "active",
            periods: isOld || outside ? null : { mahadasha: md, antardasha: ad, pratyantardasha: pd },
          },
        } }).catch(error => { if (!isOld) throw error; });
        if (isOld) finishOld();
      });
      await page.goto(origin + "/user", { waitUntil: "domcontentloaded", timeout: 60_000 });
      await page.getByRole("button", {name: "Calculate Chart", exact: true}).waitFor({ timeout: 30_000 });
      await page.getByRole("button", {name: language, exact: true}).click();
      const panel = page.getByRole("region", {name: labels.dasha.title});
      await panel.getByText(labels.dasha.calculate).waitFor();
      await page.getByRole("button", {name: labels.calculateChart, exact: true}).click();
      await panel.getByText(labels.dasha.error, {exact: true}).waitFor();
      await panel.getByRole("button", {name: labels.dasha.retry}).click();
      await panel.getByText(labels.dasha.approximate).waitFor();
      await panel.getByText(labels.dasha.historical).waitFor();
      const subperiod = panel.locator("summary").first();
      await subperiod.focus();
      await page.keyboard.press("Enter");
      assert.equal(await subperiod.evaluate(element => element.parentElement.open), true);
      assert.match(await panel.textContent(), /13:01:09\.012345 UTC/);
      const strip = panel.getByRole("group", { name: labels.dasha.timeline });
      await strip.getByRole("button").last().click();
      assert.equal(await strip.getByRole("button").last().getAttribute("aria-pressed"), "true");
      await strip.getByRole("button").first().click();
      await panel.locator("summary").first().click();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      if (process.env.KUNDALI_DASHA_SCREENSHOTS) {
        await panel.screenshot({ path: resolve(process.env.KUNDALI_DASHA_SCREENSHOTS, `dasha-${locale}.png`) });
      }

      const date = panel.getByLabel(labels.dasha.lookupDate);
      await date.fill("2010-01-01");
      await panel.getByRole("button", {name: labels.dasha.lookup, exact: true}).click();
      await oldStarted;
      await panel.getByText(labels.dasha.loading).waitFor();
      await date.fill("2131-01-01");
      await panel.getByRole("button", {name: labels.dasha.lookup, exact: true}).click();
      await panel.getByText(labels.dasha.outside).waitFor();
      releaseOld();
      await oldFinished;
      assert.equal(await panel.getByText(labels.dasha.beforeBirth).count(), 0);

      await page.getByRole("button", {name: labels.settingsButton, exact: true}).click();
      await page.getByLabel(labels.yearDaysLabel, {exact: true}).selectOption("360");
      await page.getByRole("button", {name: labels.applySettings, exact: true}).click();
      await panel.getByText(labels.dasha.recalculate).waitFor();
      assert.equal(await panel.getByRole("group", {name: labels.dasha.timeline}).count(), 0);
      await page.getByRole("button", {name: labels.settingsButton, exact: true}).click();
      await page.getByLabel(labels.yearDaysLabel, {exact: true}).selectOption("365.25");
      await page.getByRole("button", {name: labels.applySettings, exact: true}).click();
      await panel.getByText(labels.dasha.approximate).waitFor();

      if (locale === "ne") await page.getByRole("button", {name: labels.navigationToggle}).click();
      await page.getByRole("button", {name: labels.navProfiles, exact: true}).click();
      await page.getByRole("button", {name: labels.editProfileButton, exact: true}).click();
      await page.getByRole("textbox", {name: labels.formLabel, exact: true}).fill("Updated synthetic name");
      await page.getByRole("button", {name: labels.editFormSubmit, exact: true}).click();
      await page.getByText(labels.profileUpdatedNotice).waitFor();
      if (locale === "ne") await page.getByRole("button", {name: labels.navigationToggle}).click();
      await page.getByRole("button", {name: labels.navWorkspace, exact: true}).click();
      await panel.getByText(labels.dasha.calculate).waitFor();
      assert.equal(await panel.getByText(labels.dasha.historical).count(), 0);
      assert.deepEqual(errors, []);
    } finally {
      await browser.close();
    }
  });
}
