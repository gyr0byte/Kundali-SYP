import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { chromium } from "playwright";

const origin = process.env.KUNDALI_BS_ORIGIN ?? "http://127.0.0.1:3103";
for (const [locale, language, width] of [["en", "EN", 1440], ["ne", "नेपाली", 375]]) {
  test(`birth calendar validation and save at ${width}px in ${locale}`, async () => {
    const { userWorkspace: labels } = JSON.parse(
      readFileSync(new URL(`../src/i18n/${locale}.json`, import.meta.url), "utf8")
    );
    const user = {
      id: "browser-calendar-owner",
      email: "calendar-test@example.com",
      role: "user",
      language: locale,
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    };
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const jwtPart = (part) => Buffer.from(JSON.stringify(part)).toString("base64url");
    const accessToken = `${jwtPart({ alg: "HS256" })}.${jwtPart({ sub: user.id, exp })}.sig`;
    const submitted = [];
    const saved = [];
    const browser = await chromium.launch();

    try {
      const page = await browser.newPage({ viewport: { width, height: 900 }, locale });
      await page.route("**/api/auth/refresh", (route) => route.fulfill({
        json: { authenticated: true, user, access_token: accessToken, expires_at: exp * 1000 },
      }));
      const cors = {
        "access-control-allow-origin": new URL(origin).origin,
        "access-control-allow-headers": "Authorization, Content-Type",
        "access-control-allow-methods": "GET, POST, OPTIONS",
      };
      await page.route("**/api/v1/profiles**", async (route) => {
        const method = route.request().method();
        if (method === "OPTIONS") {
          return route.fulfill({ status: 204, headers: cors });
        }
        if (method === "GET") {
          return route.fulfill({
            headers: cors,
            json: { items: saved, total: saved.length, limit: 50, offset: 0 },
          });
        }
        const payload = route.request().postDataJSON();
        submitted.push(payload);
        if (payload.entered_date === "2083-12-31") {
          return route.fulfill({
            status: 422,
            headers: cors,
            json: { code: "invalid_bs_date", detail: [{ msg: "Invalid Bikram Sambat month or day" }] },
          });
        }
        const record = {
          ...payload,
          id: "8a16d42a-1670-44f1-a685-dfb9046179b6",
          owner_id: user.id,
          date_ad: "2015-04-25",
          bs_conversion_status: "resolved",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        };
        saved.push(record);
        return route.fulfill({ status: 201, headers: cors, json: record });
      });

      await page.goto(`${origin}/user`);
      await page.getByRole("button", { name: language, exact: true }).click();
      if (width < 768) {
        await page.getByRole("button", { name: labels.navigationToggle }).click();
      }
      await page.getByRole("button", { name: labels.navProfiles, exact: true }).click();
      await page.getByRole("button", { name: labels.newProfileButton }).click();
      await page.getByText(labels.formBsRange, { exact: false }).waitFor();

      await page.locator("#bp-label").fill("Browser calendar test");
      await page.locator("#bp-time").fill("08:30");
      await page.locator("#bp-place").fill("Kathmandu");
      await page.locator("#bp-tz").fill("Asia/Kathmandu");
      await page.locator("#bp-lat").fill("27.7");
      await page.locator("#bp-lon").fill("85.3");

      const submit = page.getByRole("button", { name: labels.formSubmit, exact: true });
      const date = page.locator("#bp-date");
      const dateBounds = await date.boundingBox();
      assert.ok(dateBounds && dateBounds.x >= 0 && dateBounds.x + dateBounds.width <= width);
      const expectDateIssue = async (code) => {
        await page.getByText(labels.formDateErrors[code], { exact: true }).waitFor({ timeout: 10_000 });
        assert.equal(await date.getAttribute("aria-invalid"), "true");
      };

      await page.getByRole("button", { name: "AD", exact: true }).click();
      await date.fill("1900-02-29");
      await submit.click();
      await expectDateIssue("invalid_ad_date");
      await page.getByRole("button", { name: "BS", exact: true }).click();
      await date.fill("2084-01-01");
      await submit.click();
      await expectDateIssue("bs_date_out_of_range");
      assert.equal(submitted.length, 0);

      await date.fill("2083-12-31");
      await submit.click();
      await expectDateIssue("invalid_bs_date");
      await date.fill("२०७२-०१-१२");
      assert.equal(await date.getAttribute("aria-invalid"), "false");
      await submit.click();
      await page.getByText(labels.convertedAdLabel, { exact: false }).first().waitFor();
      assert.equal(await page.locator('time[datetime="2015-04-25"]').first().textContent(), "2015-04-25");
      assert.equal(submitted.length, 2);
      assert.equal(submitted[1].entered_date, "2072-01-12");
      assert.equal(submitted[1].input_calendar, "BS");
      assert.ok(!("date_ad" in submitted[1]));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    } finally {
      await browser.close();
    }
  });
}
