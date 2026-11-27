import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

// Run against a local production build started with next start.
const origin = process.env.KUNDALI_ASTROLOGER_ORIGIN ?? "http://127.0.0.1:3102";
const screenshotDir = process.env.KUNDALI_ASTROLOGER_SCREENSHOTS;
if (screenshotDir) await mkdir(screenshotDir, { recursive: true });
const browser = await chromium.launch();
const user = {
  id: "11111111-1111-4111-8111-111111111111", email: "reviewer@example.test",
  is_active: true, language: "en", created_at: "2026-01-01T00:00:00Z",
};
const credentials = {
  display_name: "Asha Sharma", credentials: "Ten years of traditional practice.", tradition: "Vedic Jyotish",
};
const forbidden = { detail: "Approved astrologer or administrator access required" };

async function scenario({ role, queue, apply }, run) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const errors = [];
  const calls = [];
  try {
    await context.route("**/api/auth/refresh", (route) => {
      if (!role) return route.fulfill({ json: { authenticated: false } });
      const exp = Math.floor(Date.now() / 1000) + 600;
      const jwt = `test.${Buffer.from(JSON.stringify({ exp, sub: user.id, role })).toString("base64url")}.signature`;
      return route.fulfill({ json: { authenticated: true, access_token: jwt, expires_at: exp * 1000, user: { ...user, role } } });
    });
    await context.route("http://localhost:8000/api/v1/**", async (route) => {
      const request = route.request();
      const endpoint = new URL(request.url()).pathname;
      assert.ok(request.headers().authorization?.startsWith("Bearer "));
      calls.push(endpoint);
      if (endpoint === "/api/v1/review/queue") {
        assert.equal(request.method(), "GET");
        const [status, json] = typeof queue === "function" ? await queue() : queue;
        return route.fulfill({ status, json });
      }
      assert.equal(endpoint, "/api/v1/astrologer/apply");
      assert.equal(request.method(), "POST");
      assert.deepEqual(request.postDataJSON(), credentials);
      return route.fulfill(apply);
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`${origin}/astrologer`);
    await run(page, calls);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
}

async function localizedScreens(page, name, headings) {
  for (const [locale, label] of [["en", "EN"], ["ne", "नेपाली"]]) {
    await page.getByRole("button", { name: label, exact: true }).click();
    await page.getByRole("heading", { name: headings[locale], exact: true }).waitFor();
    for (const width of [1440, 768, 375, 320]) {
      await page.setViewportSize({ width, height: width < 768 ? 812 : 900 });
      await page.evaluate(() => document.fonts.ready);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `${name} overflows at ${width}px in ${locale}`);
      if (screenshotDir && [1440, 375].includes(width)) {
        await page.screenshot({ path: path.join(screenshotDir, `${name}-${locale}-${width}.png`), fullPage: true });
      }
    }
  }
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await page.setViewportSize({ width: 1440, height: 900 });
}

const visible = (page, text) => page.getByText(text, { exact: true }).waitFor();
const fillApplication = async (page) => {
  await page.getByLabel("Professional display name").fill(credentials.display_name);
  await page.getByLabel("Astrological tradition").fill(credentials.tradition);
  await page.getByLabel("Professional credentials").fill(credentials.credentials);
  await page.getByRole("button", { name: "Submit application" }).click();
};

try {
  await scenario({}, async (page, calls) => {
    await visible(page, "Sign in to continue");
    assert.equal(await page.getByRole("link", { name: "Sign in" }).getAttribute("href"), "/login?redirect=%2Fastrologer");
    assert.deepEqual(calls, []);
    await localizedScreens(page, "signed-out", { en: "Sign in to continue", ne: "अगाडि बढ्न साइन इन गर्नुहोस्" });
  });

  await scenario({ role: "user", queue: [403, forbidden], apply: {
    status: 201, json: { ...credentials, user_id: user.id, status: "pending", approved_by: null, approved_at: null },
  } }, async (page) => {
    await localizedScreens(page, "restricted", { en: "Review access is restricted", ne: "समीक्षा गर्ने पहुँच सीमित छ" });
    await page.getByRole("button", { name: "Go to professional profile" }).click();
    await localizedScreens(page, "application", { en: "Apply as an astrologer", ne: "ज्योतिषीका रूपमा आवेदन दिनुहोस्" });
    await page.getByRole("button", { name: "Submit application" }).click();
    await visible(page, "Enter a name between 2 and 100 characters.");
    await fillApplication(page);
    await localizedScreens(page, "pending", { en: "Application pending approval", ne: "आवेदन स्वीकृतिको प्रतीक्षामा छ" });
    assert.equal(await page.getByText(credentials.credentials).isVisible(), true);
    assert.equal(await page.getByRole("button", { name: "Submit application" }).count(), 0);
  });

  await scenario({ role: "user", queue: [403, forbidden], apply: {
    status: 400, json: { detail: "Application already submitted" },
  } }, async (page) => {
    await page.getByRole("button", { name: "Go to professional profile" }).click();
    await fillApplication(page);
    await visible(page, "An application already exists for this account. Its current status is unavailable here.");
    assert.equal(await page.getByText("Application pending approval", { exact: true }).count(), 0);
  });

  for (const role of ["astrologer", "admin"]) {
    await scenario({ role, queue: [200, []] }, async (page) => {
      await visible(page, "Review access verified");
      await visible(page, "Review service not yet available");
      assert.equal(await page.getByRole("button", { name: /approve|reject|edit/i }).count(), 0);
      if (role === "astrologer") {
        await localizedScreens(page, "verified", { en: "Review service not yet available", ne: "समीक्षा सेवा अझै उपलब्ध छैन" });
        await page.setViewportSize({ width: 375, height: 812 });
        await page.getByRole("button", { name: "Workspace menu" }).click();
        await page.getByRole("button", { name: "Planned features" }).click();
        await visible(page, "Knowledge contributions");
        const account = page.locator("header summary");
        await account.focus();
        await page.keyboard.press("Enter");
        await page.getByRole("button", { name: "Sign out all devices" }).click();
        await page.keyboard.press("Escape");
        assert.equal(await account.evaluate((element) => element === document.activeElement), true);
      }
    });
  }

  await scenario({ role: "astrologer", queue: [403, forbidden] }, async (page) => {
    await visible(page, "We could not confirm your approval or account standing. If your review access was suspended, contact an administrator.");
    assert.equal(await page.getByRole("button", { name: "Go to professional profile" }).count(), 0);
    assert.equal(await page.getByText("Review access verified", { exact: true }).count(), 0);
  });

  let attempt = 0;
  await scenario({ role: "astrologer", queue: () => ++attempt === 1
    ? [503, { detail: "private error detail" }]
    : [200, [{ birth_date: "private test marker" }]],
  }, async (page) => {
    await visible(page, "Review access could not be checked. Try again.");
    await page.getByRole("button", { name: "Check review access" }).click();
    await visible(page, "Review access could not be checked. Try again.");
    assert.equal(attempt, 2);
    assert.equal(await page.getByText(/private error detail|private test marker/).count(), 0);
  });
  let release;
  const heldQueue = new Promise((resolve) => { release = resolve; });
  await scenario({ role: "astrologer", queue: () => heldQueue }, async (page) => {
    await page.getByRole("status").filter({ hasText: "Checking review access…" }).waitFor();
    release([401, { detail: "Expired token" }]);
    await page.getByRole("alert").filter({ hasText: "Your session could not be verified." }).waitFor();
    assert.equal(await page.getByRole("link", { name: "Sign in" }).isVisible(), true);
  });
  console.log("Astrologer browser checks passed with mocked authentication and API routes.");
} finally {
  await browser.close();
}
