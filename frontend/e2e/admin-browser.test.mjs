import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const origin = process.env.KUNDALI_ADMIN_ORIGIN ?? "http://127.0.0.1:3102";
const screenshots = process.env.KUNDALI_ADMIN_SCREENSHOTS;
if (screenshots) await mkdir(screenshots, { recursive: true });
const browser = await chromium.launch();
const uid = (number) => `11111111-1111-4111-8111-${String(number).padStart(12, "0")}`;
const created_at = "2026-11-26T07:43:12Z";
const admin = { id: uid(1), email: "admin@example.test", role: "admin", language: "en", is_active: true, created_at };
const candidate = { user_id: uid(31), display_name: "Sample Reviewer", tradition: "Vedic Jyotish", status: "pending", approved_at: null, credentials: "PRIVATE APPLICATION TEXT" };
const event = {
  id: uid(40), actor_id: admin.id, action: "profile:update", target_type: "birth_profile", target_id: uid(41),
  created_at, ip: "192.0.2.25", metadata: { birth_date: "PRIVATE AUDIT MARKER" },
};
const text = (page, value) => page.getByText(value, { exact: true }).waitFor();
const button = (page, name) => page.getByRole("button", { name, exact: true });

async function run(role, handler, scenario) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const errors = [];
  const calls = [];
  try {
    await context.route("**/api/auth/refresh", (route) => {
      if (!role) return route.fulfill({ json: { authenticated: false } });
      const exp = Math.floor(Date.now() / 1000) + 600;
      const token = `test.${Buffer.from(JSON.stringify({ sub: admin.id, role, exp })).toString("base64url")}.signature`;
      return route.fulfill({ json: { authenticated: true, access_token: token, expires_at: exp * 1000, user: { ...admin, role } } });
    });
    await context.route("http://localhost:8000/api/v1/admin/**", async (route) => {
      const request = route.request();
      assert.ok(request.headers().authorization?.startsWith("Bearer "));
      const url = new URL(request.url());
      calls.push({ method: request.method(), path: url.pathname, search: url.search });
      return handler(route, url);
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`${origin}/admin`);
    await scenario(page, calls);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
}

async function capture(page, view, headings) {
  for (const [locale, language] of [["en", "EN"], ["ne", "नेपाली"]]) {
    await button(page, language).click();
    await page.getByRole("heading", { name: headings[locale], exact: true }).waitFor();
    for (const width of [1440, 768, 375, 320]) {
      await page.setViewportSize({ width, height: width < 768 ? 812 : 900 });
      await page.evaluate(() => document.fonts.ready);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `${view}, ${locale} overflows at ${width}`);
      if (screenshots && [1440, 375].includes(width)) {
        await page.screenshot({ path: path.join(screenshots, `${view}-${locale}-${width}.png`), fullPage: true });
      }
    }
  }
  await button(page, "EN").click();
  await page.setViewportSize({ width: 1440, height: 900 });
}

try {
  await run(null, () => assert.fail("Signed-out request"), async (page, calls) => {
    await text(page, "Sign in to continue");
    assert.equal(await page.getByRole("link", { name: "Sign in" }).getAttribute("href"), "/login?redirect=%2Fadmin");
    assert.deepEqual(calls, []);
  });
  await run("astrologer", () => assert.fail("Non-admin request"), async (page, calls) => {
    await text(page, "Administrator access is required.");
    assert.deepEqual(calls, []);
  });
  for (const status of [401, 403]) {
    await run("admin", (route) => route.fulfill({ status, json: { detail: "PRIVATE ERROR" } }), async (page) => {
      await text(page, status === 401 ? "Your session has expired. Sign in again to continue." : "Administrator access is required.");
      assert.equal(await page.getByRole("table").count(), 0);
      assert.equal(await page.getByText("PRIVATE ERROR").count(), 0);
    });
  }

  const users = [admin, ...Array.from({ length: 21 }, (_, index) => ({
    ...admin, id: uid(index + 2), email: `member-${String(index + 1).padStart(2, "0")}@example.test`,
    role: index === 1 ? "admin" : "user",
  }))];
  const astrologers = [{ ...candidate }];
  let rejectAudit = false;
  let staleOnRead = false;
  let releaseInitial;
  const initialRead = new Promise((resolve) => { releaseInitial = resolve; });
  await run("admin", async (route, url) => {
    const [, , , , section, id, action] = url.pathname.split("/");
    const items = section === "users" ? users : section === "astrologers" ? astrologers : [event];
    if (action) {
      const record = items.find((row) => (row.id ?? row.user_id) === id);
      assert.ok(record);
      if (action === "deactivate" && record.role === "admin") {
        return route.fulfill({ status: 400, json: { detail: "Cannot deactivate the last admin" } });
      }
      if (action === "deactivate" || action === "reactivate") record.is_active = action === "reactivate";
      else {
        record.status = action === "approve" ? "approved" : "suspended";
        if (action === "approve") record.approved_at = created_at;
      }
      return route.fulfill({ status: 204 });
    }
    const offset = Number(url.searchParams.get("offset"));
    const limit = Number(url.searchParams.get("limit"));
    if (limit === 1) await initialRead;
    if (section === "audit" && rejectAudit) return route.fulfill({ status: 500, json: { detail: "PRIVATE ERROR" } });
    if (section === "users" && staleOnRead) {
      staleOnRead = false;
      users[1].is_active = false;
    }
    const filters = { role: "role", is_active: "is_active", status: "status" };
    const filtered = items.filter((row) => Object.entries(filters).every(([param, key]) =>
      !url.searchParams.has(param) || String(row[key]) === url.searchParams.get(param)));
    return route.fulfill({ json: { items: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit } });
  }, async (page, calls) => {
    await text(page, "Loading records…");
    releaseInitial();
    await text(page, "22");
    await capture(page, "overview", { en: "Overview", ne: "समग्र विवरण" });
    await button(page, "User management").click();
    const self = page.getByRole("row").filter({ hasText: admin.email });
    await self.waitFor();
    assert.equal(await self.getByRole("button").count(), 0);
    await capture(page, "users", { en: "User management", ne: "प्रयोगकर्ता व्यवस्थापन" });
    await button(page, "Next").click();
    await text(page, "21–22 of 22");
    await button(page, "Previous").click();
    await text(page, "1–20 of 22");

    const member = page.getByRole("row").filter({ hasText: users[1].email });
    await member.getByRole("button", { name: "Deactivate" }).click();
    const dialog = page.getByRole("dialog", { name: "Deactivate" });
    await dialog.waitFor();
    assert.match(await dialog.innerText(), /member-01@example\.test/);
    assert.ok(!calls.some(({ method }) => method === "POST"));
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    await member.getByRole("button", { name: "Deactivate" }).click();
    staleOnRead = true;
    await button(page, "Confirm action").click();
    await text(page, "The record changed or moved. Review the refreshed list before acting.");
    assert.ok(!calls.some(({ method }) => method === "POST"));
    const confirmRowAction = async (row, action) => {
      await row.getByRole("button", { name: action, exact: true }).click();
      await button(page, "Confirm action").evaluate((element) => {
        element.click();
        element.click();
      });
      await text(page, "The change was saved.");
    };
    await confirmRowAction(member, "Reactivate");
    await confirmRowAction(member, "Deactivate");
    await page.getByLabel("Role", { exact: true }).selectOption("admin");
    await text(page, "1–2 of 2");
    await page.getByLabel("Status", { exact: true }).selectOption("inactive");
    await text(page, "No records match this view.");
    await page.getByLabel("Status", { exact: true }).selectOption("active");
    const otherAdmin = page.getByRole("row").filter({ hasText: users[2].email });
    await otherAdmin.getByRole("button", { name: "Deactivate" }).click();
    await button(page, "Confirm action").click();
    await text(page, "The account cannot be deactivated. Your own account and the last active administrator are protected.");
    assert.ok(calls.some(({ search }) => search.includes("role=admin") && search.includes("is_active=false")));

    await button(page, "Astrologer approvals").click();
    const reviewer = page.getByRole("row").filter({ hasText: candidate.display_name });
    await reviewer.waitFor();
    assert.equal(await page.getByText("PRIVATE APPLICATION TEXT").count(), 0);
    await capture(page, "astrologers", { en: "Astrologer approvals", ne: "ज्योतिषी स्वीकृति" });
    await page.getByLabel("Status", { exact: true }).selectOption("pending");
    await confirmRowAction(reviewer, "Approve");
    await text(page, "No records match this view.");
    await page.getByLabel("Status", { exact: true }).selectOption("");
    await confirmRowAction(reviewer, "Suspend");
    assert.equal(calls.filter(({ method }) => method === "POST").length, 5);

    rejectAudit = true;
    await button(page, "Audit logs").click();
    await text(page, "Records could not be loaded. Try again.");
    rejectAudit = false;
    await button(page, "Refresh").click();
    await text(page, "Birth profile updated");
    assert.equal(await page.getByText(/PRIVATE ERROR|PRIVATE AUDIT MARKER|192\.0\.2\.25/).count(), 0);
    await capture(page, "audit", { en: "Audit logs", ne: "लेखापरीक्षण अभिलेख" });
    await page.setViewportSize({ width: 375, height: 812 });
    await button(page, "Console menu").click();
    await button(page, "Planned features").click();
    await text(page, "Calculation analytics");
    assert.equal(await page.getByText("Unavailable", { exact: true }).count(), 4);
    assert.deepEqual(await page.evaluate(() => Object.keys(localStorage)), []);
  });
  console.log("Admin Playwright checks passed with mocked authentication and API routes.");
} finally {
  await browser.close();
}
