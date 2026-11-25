import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = path.resolve(__dirname, "..");
const TEST_PORT = 3101;
const TEST_ORIGIN = `http://127.0.0.1:${TEST_PORT}`;

const MOCK_USER = {
  id: "u-browser-1",
  email: "asha@example.com",
  role: "user",
  language: "ne",
  is_active: true,
  created_at: "2026-11-25T10:00:00Z",
};

function makeJwtWithExp(expSeconds) {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(
    JSON.stringify({ sub: MOCK_USER.id, role: MOCK_USER.role, exp: expSeconds })
  ).toString("base64url");
  return `${header}.${payload}.sig`;
}

async function waitForServerReady(baseUrl, timeoutMs = 45_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${baseUrl}/login`, { redirect: "manual" });
      if (res.status >= 200 && res.status < 500) {
        return;
      }
    } catch {
      // Server still booting
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`Timed out waiting for Next.js dev server at ${baseUrl}`);
}

async function assertResponsiveNoOverflow(page, routeLabel, viewports) {
  for (const vp of viewports) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    const metrics = await page.evaluate(() => {
      const controls = [...document.querySelectorAll("a, button, input, select, textarea")].filter(
        (el) => !el.hasAttribute("data-nextjs-dev-tools-button") && !el.closest("nextjs-portal")
      );
      const visible = controls
        .map((el) => {
          const cs = getComputedStyle(el);
          const r = el.getBoundingClientRect();
          const isSrOnly = r.width <= 1 && r.height <= 1 && cs.overflow === "hidden";
          return {
            tag: el.tagName,
            text: (el.textContent || el.getAttribute("aria-label") || el.id || "").trim().slice(0, 35),
            left: r.left,
            right: r.right,
            top: r.top,
            bottom: r.bottom,
            width: r.width,
            height: r.height,
            visible: !isSrOnly && cs.visibility !== "hidden" && r.width > 0 && r.height > 0,
          };
        })
        .filter((c) => c.visible);

      const clipped = visible.filter((c) => c.right > window.innerWidth + 1 || c.left < -1);
      const overlaps = [];
      for (let i = 0; i < visible.length; i += 1) {
        for (let j = i + 1; j < visible.length; j += 1) {
          const a = visible[i];
          const b = visible[j];
          // Allow small tolerance cleanly; detect actual UI overlaps
          if (
            a.left + 2 < b.right &&
            a.right - 2 > b.left &&
            a.top + 2 < b.bottom &&
            a.bottom - 2 > b.top
          ) {
            overlaps.push([a.text, b.text]);
          }
        }
      }

      return {
        innerWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        clipped,
        overlaps,
      };
    });

    assert.ok(
      metrics.scrollWidth <= metrics.innerWidth,
      `${routeLabel} overflow at ${vp.width}x${vp.height}: scrollWidth=${metrics.scrollWidth} > innerWidth=${metrics.innerWidth}`
    );
    assert.equal(
      metrics.clipped.length,
      0,
      `${routeLabel} clipped controls at ${vp.width}x${vp.height}: ${JSON.stringify(metrics.clipped)}`
    );
    assert.equal(
      metrics.overlaps.length,
      0,
      `${routeLabel} overlapping controls at ${vp.width}x${vp.height}: ${JSON.stringify(metrics.overlaps)}`
    );
  }
}

async function runTests() {
  let serverProc = null;
  let browser = null;

  try {
    const nextBin = path.join(FRONTEND_DIR, "node_modules/next/dist/bin/next");
    serverProc = spawn(process.execPath, [nextBin, "dev", "-H", "127.0.0.1", "-p", String(TEST_PORT)], {
      cwd: FRONTEND_DIR,
      env: {
        ...process.env,
        KUNDALI_FRONTEND_ORIGIN: TEST_ORIGIN,
        KUNDALI_API_BASE_URL: "https://api.kundali.local/api/v1",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });

    await waitForServerReady(TEST_ORIGIN);

    browser = await chromium.launch({ headless: true });
    const viewports = [
      { width: 1280, height: 800 },
      { width: 768, height: 1024 },
      { width: 375, height: 812 },
    ];

    // ------------------------------------------------------------------
    // 1. Clean unauthenticated BFF boot across /login, /register, /user
    // ------------------------------------------------------------------
    {
      const context = await browser.newContext();
      const page = await context.newPage();
      const consoleErrors = [];
      const pageErrors = [];
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push(msg.text());
      });
      page.on("pageerror", (err) => pageErrors.push(err.message));

      // Wait for initial real POST /api/auth/refresh -> 200 { authenticated: false }
      const refreshResponsePromise = page.waitForResponse(
        (res) => res.url() === `${TEST_ORIGIN}/api/auth/refresh` && res.request().method() === "POST"
      );
      await page.goto(`${TEST_ORIGIN}/login`, { waitUntil: "domcontentloaded" });
      const refreshRes = await refreshResponsePromise;
      assert.equal(refreshRes.status(), 200);
      assert.equal((await refreshRes.json()).authenticated, false);

      await page.locator("#login-email").waitFor({ state: "visible" });
      assert.equal(
        await page.getByText("Authentication Service Temporarily Unavailable").count(),
        0
      );

      // Verify explicit labels, IDs, autocomplete, and Observatory colors
      const loginMeta = await page.evaluate(() => {
        const emailEl = document.getElementById("login-email");
        const passEl = document.getElementById("login-password");
        return {
          emailLabel: document.querySelector('label[for="login-email"]')?.textContent?.trim(),
          emailType: emailEl?.getAttribute("type"),
          emailAutocomplete: emailEl?.getAttribute("autocomplete"),
          passLabel: document.querySelector('label[for="login-password"]')?.textContent?.trim(),
          passType: passEl?.getAttribute("type"),
          passAutocomplete: passEl?.getAttribute("autocomplete"),
          bodyBg: getComputedStyle(document.body).backgroundColor,
          bodyBgImage: getComputedStyle(document.body).backgroundImage,
        };
      });
      assert.equal(loginMeta.emailLabel, "Email address");
      assert.equal(loginMeta.emailType, "email");
      assert.equal(loginMeta.emailAutocomplete, "email");
      assert.equal(loginMeta.passLabel, "Password");
      assert.equal(loginMeta.passType, "password");
      assert.equal(loginMeta.passAutocomplete, "current-password");
      assert.equal(loginMeta.bodyBg, "rgb(247, 246, 241)");
      assert.equal(loginMeta.bodyBgImage, "none");

      // Client-side validation + language toggle preserving email
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      await page.locator("#login-form-error").waitFor({ state: "visible" });
      assert.match(await page.locator("#login-form-error").innerText(), /Enter a valid email address/);

      await page.locator("#login-email").fill("asha@example.com");
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      assert.match(await page.locator("#login-form-error").innerText(), /Enter your password/);

      await page.getByRole("button", { name: "नेपाली", exact: true }).click();
      assert.equal(await page.getByRole("heading", { level: 1 }).innerText(), "साइन इन गर्नुहोस्");
      assert.match(await page.locator("#login-form-error").innerText(), /आफ्नो पासवर्ड लेख्नुहोस्/);
      assert.equal(await page.locator("#login-email").inputValue(), "asha@example.com");

      await page.getByRole("button", { name: "EN", exact: true }).click();
      assert.equal(await page.locator("#login-email").inputValue(), "asha@example.com");

      // Check /login?registered=1 banner & safe redirect render
      await page.goto(`${TEST_ORIGIN}/login?registered=1&redirect=//evil.example`, {
        waitUntil: "domcontentloaded",
      });
      await page.getByText("Account created successfully").waitFor({ state: "visible" });
      const evilDomLeak = await page.evaluate(() => {
        const panelHtml = document.getElementById("auth-form-panel")?.innerHTML ?? "";
        const badLinks = [...document.querySelectorAll("a")].some((a) =>
          (a.getAttribute("href") ?? "").includes("evil.example")
        );
        return panelHtml.includes("evil.example") || badLinks;
      });
      assert.equal(evilDomLeak, false);

      await assertResponsiveNoOverflow(page, "/login", viewports);

      // Navigate via link to /register
      await page.getByRole("link", { name: "Create account" }).click();
      await page.waitForURL(`${TEST_ORIGIN}/register`);
      await page.locator("#register-email").waitFor({ state: "visible" });

      assert.equal(await page.locator('meter, progress, [role="progressbar"]').count(), 0);
      assert.equal(await page.locator("#register-password").getAttribute("minlength"), "10");
      assert.equal(await page.locator("#register-password").getAttribute("maxlength"), "128");
      assert.match(
        await page.locator("#register-password-rules").innerText(),
        /10 to 128 characters/
      );

      await page.locator("#register-email").fill("user@example.com");
      await page.locator("#register-password").fill("short9");
      await page.locator("#register-confirm-password").fill("short9");
      await page.getByRole("button", { name: "Create account", exact: true }).click();
      assert.match(
        await page.locator("#register-form-error").innerText(),
        /Password must be at least 10 characters/
      );

      await page.getByRole("button", { name: "नेपाली", exact: true }).click();
      assert.equal(
        await page.getByRole("heading", { level: 1 }).innerText(),
        "खाता सिर्जना गर्नुहोस्"
      );
      assert.equal(await page.locator("#register-email").inputValue(), "user@example.com");
      await page.getByRole("button", { name: "EN", exact: true }).click();

      await page.locator("#register-password").fill("ValidPass123!");
      await page.locator("#register-confirm-password").fill("MismatchPass123!");
      await page.getByRole("button", { name: "Create account", exact: true }).click();
      assert.match(
        await page.locator("#register-form-error").innerText(),
        /Password and confirm password must match/
      );

      await assertResponsiveNoOverflow(page, "/register", viewports);

      // Navigate to /user workspace cleanly
      await page.goto(`${TEST_ORIGIN}/user`, { waitUntil: "domcontentloaded" });
      await page.getByText("Authentication Required to Manage Saved Profiles").waitFor({
        state: "visible",
      });
      await assertResponsiveNoOverflow(page, "/user(unauthenticated)", viewports);

      assert.equal(await page.getByRole("link", { name: "Sign in" }).count(), 2);
      assert.equal(await page.getByRole("link", { name: "Create account" }).count(), 2);
      assert.equal(
        await page.getByRole("button", { name: "Save Profile", exact: true }).isDisabled(),
        true
      );

      // Preview Synthetic Sample works cleanly with zero storage usage
      await page.getByRole("button", { name: /Preview Synthetic Sample/ }).first().click();
      await page.getByText("Synthetic Engine Snapshot").waitFor({ state: "visible" });
      await page.getByRole("button", { name: "South Indian" }).click();
      await assertResponsiveNoOverflow(page, "/user(synthetic)", viewports);

      const storageState = await page.evaluate(() => ({
        localLen: localStorage.length,
        sessionLen: sessionStorage.length,
        cookie: document.cookie,
      }));
      assert.deepEqual(storageState, { localLen: 0, sessionLen: 0, cookie: "" });
      assert.deepEqual(consoleErrors, []);
      assert.deepEqual(pageErrors, []);
      await context.close();
    }

    // ------------------------------------------------------------------
    // 2. Login errors (401, 429 Retry-After, duplicate-submit), recovery, & safe redirect
    // ------------------------------------------------------------------
    {
      const futureExpSec = Math.floor((Date.now() + 900_000) / 1000);
      const validJwt = makeJwtWithExp(futureExpSec);
      let isAuthedServer = false;
      let loginMode = "invalid";
      let loginRecoveryStarted = false;
      let refreshAttemptAfterRecovery = 0;
      let loginPostCount = 0;
      let delayedLoginResolver = null;

      const context = await browser.newContext();
      await context.route("**/api/auth/**", async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/refresh") {
          if (loginMode === "recovery_then_ok" && loginRecoveryStarted) {
            refreshAttemptAfterRecovery += 1;
            if (refreshAttemptAfterRecovery === 1) {
              await route.fulfill({
                status: 503,
                contentType: "application/json",
                body: JSON.stringify({
                  code: "BACKEND_UNAVAILABLE",
                  message: "Temporarily unavailable",
                }),
              });
              return;
            }
            isAuthedServer = true;
            await route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({
                authenticated: true,
                access_token: validJwt,
                expires_at: futureExpSec * 1000,
                user: MOCK_USER,
              }),
            });
            return;
          }
          if (!isAuthedServer) {
            await route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ authenticated: false }),
            });
            return;
          }
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              authenticated: true,
              access_token: validJwt,
              expires_at: futureExpSec * 1000,
              user: MOCK_USER,
            }),
          });
          return;
        }
        if (url.pathname === "/api/auth/login") {
          loginPostCount += 1;
          if (loginMode === "invalid") {
            await route.fulfill({
              status: 401,
              contentType: "application/json",
              body: JSON.stringify({ code: "INVALID_CREDENTIALS", message: "Invalid" }),
            });
            return;
          }
          if (loginMode === "rate_limit_header") {
            await route.fulfill({
              status: 429,
              headers: { "retry-after": "45" },
              contentType: "application/json",
              body: JSON.stringify({ code: "RATE_LIMITED", message: "Rate limited" }),
            });
            return;
          }
          if (loginMode === "rate_limit_no_header") {
            await route.fulfill({
              status: 429,
              contentType: "application/json",
              body: JSON.stringify({ code: "RATE_LIMITED", message: "Rate limited" }),
            });
            return;
          }
          if (loginMode === "recovery_then_ok") {
            loginRecoveryStarted = true;
            await route.fulfill({
              status: 503,
              contentType: "application/json",
              body: JSON.stringify({
                code: "PROFILE_FETCH_FAILED",
                message: "Profile unavailable",
                session_established: true,
              }),
            });
            return;
          }
          if (loginMode === "delayed_success") {
            await new Promise((resolve) => {
              delayedLoginResolver = resolve;
            });
            isAuthedServer = true;
            await route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({
                authenticated: true,
                access_token: validJwt,
                expires_at: futureExpSec * 1000,
                user: MOCK_USER,
              }),
            });
            return;
          }
        }
        if (url.pathname === "/api/auth/logout") {
          isAuthedServer = false;
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              local_cookie_cleared: true,
              backend_logout_request_completed: false,
              backend_revocation_state: "backend_unconfirmed",
            }),
          });
          return;
        }
        if (url.pathname === "/api/auth/logout-all") {
          await route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({
              code: "BACKEND_UNAVAILABLE",
              message: "Backend down",
              local_cookie_cleared: false,
              backend_logout_request_completed: false,
              backend_revocation_state: "backend_unconfirmed",
            }),
          });
          return;
        }
        await route.continue();
      });

      await context.route("http://localhost:8000/api/v1/profiles*", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }),
        });
      });

      const page = await context.newPage();
      await page.goto(`${TEST_ORIGIN}/login?redirect=//evil.example`, { waitUntil: "domcontentloaded" });
      await page.locator("#login-email").waitFor({ state: "visible" });

      await page.locator("#login-email").fill("asha@example.com");
      await page.locator("#login-password").fill("WrongPassword123!");
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      await page.locator("#login-form-error").waitFor({ state: "visible" });
      assert.match(await page.locator("#login-form-error").innerText(), /Invalid email or password/);
      assert.equal(await page.locator("#login-email").inputValue(), "asha@example.com");

      loginMode = "rate_limit_header";
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      assert.match(await page.locator("#login-form-error").innerText(), /45 seconds/);

      loginMode = "rate_limit_no_header";
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      assert.match(
        await page.locator("#login-form-error").innerText(),
        /Please wait before trying again/
      );

      // Duplicate submission prevention while delayed login is in flight + safe redirect to /user (rejecting //evil.example)
      const countBeforeSlow = loginPostCount;
      loginMode = "delayed_success";
      const submitBtn = page.getByRole("button", { name: /^(Sign in|Signing in…)$/ });
      await submitBtn.click();
      assert.equal(await submitBtn.isDisabled(), true);
      await submitBtn.click({ force: true });
      await new Promise((r) => setTimeout(r, 40));
      assert.equal(loginPostCount - countBeforeSlow, 1);

      delayedLoginResolver();
      await page.waitForURL(`${TEST_ORIGIN}/user`);
      await page.getByText("asha@example.com").waitFor({ state: "visible" });
      await page.getByText(/Role:\s*user/i).waitFor({ state: "visible" });

      // Responsive authenticated header on /user (no overflow)
      await assertResponsiveNoOverflow(page, "/user(authenticated)", viewports);

      // Visiting /login while authenticated auto-redirects to /user
      await page.goto(`${TEST_ORIGIN}/login`, { waitUntil: "domcontentloaded" });
      await page.waitForURL(`${TEST_ORIGIN}/user`);

      // Sign out all devices dialog + failed 503 preserves session honestly
      await page.getByRole("button", { name: "Sign out all devices" }).click();
      const dialog = page.getByRole("alertdialog");
      await dialog.waitFor({ state: "visible" });
      assert.match(await dialog.innerText(), /15 minutes/);
      await dialog.getByRole("button", { name: "Revoke all sessions" }).click();
      await page.getByText(/Global sign-out did not complete/).waitFor({ state: "visible" });
      assert.equal(
        await page.getByRole("button", { name: "Sign out", exact: true }).isVisible(),
        true
      );

      // Single-session Sign out with unconfirmed backend revocation displays honest amber notice
      await page.getByRole("button", { name: "Sign out", exact: true }).click();
      await page
        .getByText(/backend refresh-token revocation could not be confirmed/i)
        .waitFor({ state: "visible" });
      assert.equal(await page.getByRole("link", { name: "Sign in" }).count() >= 1, true);

      // Recovery login flow (session_established: true -> Retry session -> /user)
      isAuthedServer = false;
      loginMode = "recovery_then_ok";
      await page.goto(`${TEST_ORIGIN}/login`, { waitUntil: "domcontentloaded" });
      await page.locator("#login-email").fill("asha@example.com");
      await page.locator("#login-password").fill("ValidPass123!");
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      const retryBtn = page.getByRole("button", { name: "Retry session" });
      await retryBtn.waitFor({ state: "visible" });
      await retryBtn.click();
      await page.waitForURL(`${TEST_ORIGIN}/user`);
      await page.getByText("asha@example.com").waitFor({ state: "visible" });

      await context.close();
    }

    // ------------------------------------------------------------------
    // 3. Registration 400/422 errors & 201 root UserResponse redirect without auto-login
    // ------------------------------------------------------------------
    {
      let registerCalls = 0;
      let autoAuthCallsAfterRegister = 0;
      let registerMode = "duplicate";

      const context = await browser.newContext();
      await context.route("**/api/auth/**", async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === "/api/auth/refresh") {
          if (registerCalls > 0) autoAuthCallsAfterRegister += 1;
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ authenticated: false }),
          });
          return;
        }
        if (url.pathname === "/api/auth/login") {
          autoAuthCallsAfterRegister += 1;
          await route.fulfill({ status: 500, body: "{}" });
          return;
        }
        if (url.pathname === "/api/auth/register") {
          registerCalls += 1;
          if (registerMode === "duplicate") {
            await route.fulfill({
              status: 400,
              contentType: "application/json",
              body: JSON.stringify({
                code: "REGISTRATION_REJECTED",
                message: "Email already registered.",
              }),
            });
            return;
          }
          await route.fulfill({
            status: 201,
            contentType: "application/json",
            body: JSON.stringify(MOCK_USER),
          });
          return;
        }
        await route.continue();
      });

      const page = await context.newPage();
      await page.goto(`${TEST_ORIGIN}/register`, { waitUntil: "domcontentloaded" });
      await page.locator("#register-email").fill("asha@example.com");
      await page.locator("#register-password").fill("ValidPassword123!");
      await page.locator("#register-confirm-password").fill("ValidPassword123!");
      await page.getByRole("button", { name: "Create account", exact: true }).click();
      await page.locator("#register-form-error").waitFor({ state: "visible" });
      assert.match(
        await page.locator("#register-form-error").innerText(),
        /already registered/i
      );

      registerMode = "ok";
      await page.getByRole("button", { name: "Create account", exact: true }).click();
      await page.waitForURL(`${TEST_ORIGIN}/login?registered=1`);
      await page.getByText("Account created successfully").waitFor({ state: "visible" });
      assert.equal(autoAuthCallsAfterRegister, 0);

      await context.close();
    }

    console.log("ALL PLAYWRIGHT E2E CHROMIUM CHECKS PASSED.");
  } finally {
    if (browser) {
      await browser.close();
    }
    if (serverProc && !serverProc.killed) {
      serverProc.kill("SIGTERM");
    }
  }
}

await runTests();
