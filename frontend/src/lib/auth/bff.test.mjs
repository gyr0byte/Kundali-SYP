import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(__dirname, "../..");

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      const mapped = path.join(SRC_ROOT, specifier.slice(2));
      for (const ext of ["", ".ts", ".tsx", ".json"]) {
        const candidate = `${mapped}${ext}`;
        try {
          readFileSync(candidate);
          return nextResolve(pathToFileURL(candidate).href, context);
        } catch {
          // Try next extension
        }
      }
    }
    if (specifier.startsWith(".") && context.parentURL?.startsWith("file:")) {
      const parentDir = path.dirname(fileURLToPath(context.parentURL));
      const base = path.resolve(parentDir, specifier);
      for (const ext of ["", ".ts", ".tsx", ".json"]) {
        const candidate = `${base}${ext}`;
        try {
          readFileSync(candidate);
          return nextResolve(pathToFileURL(candidate).href, context);
        } catch {
          // Try next extension
        }
      }
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.startsWith("file:") && (url.endsWith(".tsx") || url.endsWith(".ts"))) {
      const source = readFileSync(fileURLToPath(url), "utf8");
      const transpiled = ts.transpileModule(source, {
        fileName: fileURLToPath(url),
        compilerOptions: {
          module: ts.ModuleKind.ESNext,
          target: ts.ScriptTarget.ES2022,
          esModuleInterop: true,
        },
      });
      return {
        format: "module",
        shortCircuit: true,
        source: transpiled.outputText,
      };
    }
    return nextLoad(url, context);
  },
});

const {
  CSRF_HEADER_NAME,
  CSRF_HEADER_VALUE,
  REFRESH_COOKIE_MAX_AGE_SECONDS,
  REFRESH_COOKIE_NAME,
  REFRESH_COOKIE_PATH,
  buildClearRefreshCookieHeader,
  buildSetRefreshCookieHeader,
  extractAccessTokenExpiresAtMs,
  handleLogin,
  handleLogout,
  handleLogoutAll,
  handleRefresh,
  handleRegister,
  joinBackendUrl,
  normalizeBackendApiBaseUrl,
  normalizeTrustedFrontendOrigin,
  readRefreshCookieFromRequest,
} = await import("./bff.ts");

const { POST: registerRoutePost } = await import("../../app/api/auth/register/route.ts");
const { POST: loginRoutePost } = await import("../../app/api/auth/login/route.ts");
const { POST: refreshRoutePost } = await import("../../app/api/auth/refresh/route.ts");
const { POST: logoutRoutePost } = await import("../../app/api/auth/logout/route.ts");
const { POST: logoutAllRoutePost } = await import("../../app/api/auth/logout-all/route.ts");

function makeJwtWithExp(expSeconds) {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(
    JSON.stringify({ sub: "user-123", role: "user", exp: expSeconds })
  ).toString("base64url");
  return `${header}.${payload}.signature`;
}

function makeBffRequest(url, options = {}) {
  const headers = new Headers(options.headers ?? {});
  if (options.includeOrigin !== false && !headers.has("origin")) {
    headers.set("origin", options.origin ?? "http://localhost:3000");
  }
  if (options.includeCsrf !== false && !headers.has(CSRF_HEADER_NAME)) {
    headers.set(CSRF_HEADER_NAME, CSRF_HEADER_VALUE);
  }
  if (options.cookie) {
    headers.set("cookie", options.cookie);
  }
  if (options.body !== undefined && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  return new Request(url, {
    method: options.method ?? "POST",
    headers,
    body: options.body,
  });
}

function assertNoStoreHeaders(res) {
  assert.equal(res.headers.get("cache-control"), "no-store, private");
  assert.equal(res.headers.get("pragma"), "no-cache");
  assert.equal(res.headers.get("vary"), "Cookie");
  assert.equal(res.headers.get("access-control-allow-origin"), null);
}

const SAMPLE_USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "asha@example.com",
  role: "user",
  language: "en",
  is_active: true,
  created_at: "2026-11-25T10:00:00Z",
};

describe("BFF configuration, URL normalization, and cookie attributes", () => {
  it("normalizes development URLs and requires explicit HTTPS URLs in production", () => {
    assert.equal(
      normalizeBackendApiBaseUrl(undefined, false),
      "http://127.0.0.1:8000/api/v1"
    );
    assert.equal(
      normalizeBackendApiBaseUrl("http://127.0.0.1:8000/api/v1///", false),
      "http://127.0.0.1:8000/api/v1"
    );
    assert.equal(
      joinBackendUrl("http://127.0.0.1:8000/api/v1/", "/auth/login"),
      "http://127.0.0.1:8000/api/v1/auth/login"
    );
    assert.equal(
      joinBackendUrl("http://127.0.0.1:8000/api/v1", "auth/refresh"),
      "http://127.0.0.1:8000/api/v1/auth/refresh"
    );

    assert.throws(() => normalizeBackendApiBaseUrl(undefined, true));
    assert.throws(() => normalizeBackendApiBaseUrl("http://api.kundali.example/api/v1", true));
    assert.throws(() =>
      normalizeBackendApiBaseUrl("https://user:pass@api.kundali.example/api/v1", true)
    );
    assert.equal(
      normalizeBackendApiBaseUrl("https://api.kundali.example/api/v1/", true),
      "https://api.kundali.example/api/v1"
    );

    assert.equal(normalizeTrustedFrontendOrigin(undefined, false), "http://localhost:3000");
    assert.throws(() => normalizeTrustedFrontendOrigin(undefined, true));
    assert.throws(() => normalizeTrustedFrontendOrigin("http://app.kundali.example", true));
    assert.throws(() => normalizeTrustedFrontendOrigin("https://app.kundali.example/user", true));
    assert.equal(
      normalizeTrustedFrontendOrigin("https://app.kundali.example/", true),
      "https://app.kundali.example"
    );
  });

  it("sets and clears HttpOnly SameSite=Lax Path=/api/auth refresh cookie safely", () => {
    assert.equal(REFRESH_COOKIE_NAME, "kundali_refresh_token");
    assert.equal(REFRESH_COOKIE_PATH, "/api/auth");
    assert.equal(REFRESH_COOKIE_MAX_AGE_SECONDS, 7 * 24 * 60 * 60);

    const devCookie = buildSetRefreshCookieHeader("refresh_secret_1", { isProduction: false });
    assert.match(devCookie, /kundali_refresh_token=refresh_secret_1/);
    assert.match(devCookie, /HttpOnly/);
    assert.match(devCookie, /SameSite=Lax/);
    assert.match(devCookie, /Path=\/api\/auth/);
    assert.match(devCookie, /Max-Age=604800/);
    assert.equal(devCookie.includes("Secure"), false);

    const prodCookie = buildSetRefreshCookieHeader("refresh_secret_2", { isProduction: true });
    assert.match(prodCookie, /; Secure$/);

    const clearProd = buildClearRefreshCookieHeader({ isProduction: true });
    assert.match(clearProd, /^kundali_refresh_token=;/);
    assert.match(clearProd, /Path=\/api\/auth/);
    assert.match(clearProd, /Max-Age=0/);
    assert.match(clearProd, /HttpOnly/);
    assert.match(clearProd, /SameSite=Lax/);
    assert.match(clearProd, /Secure/);

    const req = makeBffRequest("http://localhost:3000/api/auth/refresh", {
      cookie: "theme=paper; kundali_refresh_token=tok_abc%3D%3D; other=1",
    });
    assert.equal(readRefreshCookieFromRequest(req), "tok_abc==");
  });
});

describe("BFF CSRF and Origin validation", () => {
  it("rejects missing Origin, mismatched Origin (even with spoofed Host), missing CSRF header, and non-JSON forms", async () => {
    let backendCalled = false;
    const spyFetch = async () => {
      backendCalled = true;
      throw new Error("Backend should never be called when CSRF fails");
    };

    const badRequests = [
      makeBffRequest("http://localhost:3000/api/auth/login", {
        includeOrigin: false,
        body: JSON.stringify({ email: "a@b.com", password: "Password123!" }),
      }),
      makeBffRequest("http://localhost:3000/api/auth/login", {
        origin: "https://evil.example",
        headers: { "x-forwarded-host": "localhost:3000", host: "localhost:3000" },
        body: JSON.stringify({ email: "a@b.com", password: "Password123!" }),
      }),
      makeBffRequest("http://localhost:3000/api/auth/refresh", {
        origin: "http://localhost:3001",
      }),
      makeBffRequest("http://localhost:3000/api/auth/refresh", {
        includeCsrf: false,
      }),
      makeBffRequest("http://localhost:3000/api/auth/logout", {
        headers: { [CSRF_HEADER_NAME]: "invalid" },
      }),
    ];

    for (const req of badRequests) {
      const res = await handleRefresh(req, { fetchImpl: spyFetch, isProduction: false });
      assert.equal(res.status, 403);
      assertNoStoreHeaders(res);
    }

    const formReq = new Request("http://localhost:3000/api/auth/login", {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
        [CSRF_HEADER_NAME]: CSRF_HEADER_VALUE,
        "content-type": "application/x-www-form-urlencoded",
      },
      body: "email=a%40b.com&password=Password123!",
    });
    const formRes = await handleLogin(formReq, { fetchImpl: spyFetch, isProduction: false });
    assert.equal(formRes.status, 415);
    assertNoStoreHeaders(formRes);
    assert.equal(backendCalled, false);
  });

  it("never leaks config URLs when production env vars are missing", async () => {
    const req = makeBffRequest("https://app.kundali.example/api/auth/refresh", {
      origin: "https://app.kundali.example",
    });
    const res = await handleRefresh(req, {
      isProduction: true,
      apiBaseUrl: "",
      frontendOrigin: "https://app.kundali.example",
    });
    assert.equal(res.status, 500);
    assertNoStoreHeaders(res);
    const body = await res.text();
    assert.equal(body.includes("127.0.0.1"), false);
  });
});

describe("BFF register and login routes", () => {
  it("forwards registration without auto-login and maps backend errors without leaking password", async () => {
    const calls = [];
    const mockFetch = async (url, init) => {
      calls.push({ url, init });
      const body = JSON.parse(init.body);
      if (body.email === "dup@example.com") {
        return new Response(JSON.stringify({ detail: "Email already registered" }), {
          status: 400,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(JSON.stringify(SAMPLE_USER), {
        status: 201,
        headers: { "content-type": "application/json" },
      });
    };

    const secretPass = "SuperSecretPassword2026!";
    const okReq = makeBffRequest("http://localhost:3000/api/auth/register", {
      body: JSON.stringify({ email: "asha@example.com", password: secretPass }),
    });
    const okRes = await handleRegister(okReq, { fetchImpl: mockFetch, isProduction: false });
    assert.equal(okRes.status, 201);
    assert.equal(okRes.headers.get("set-cookie"), null);
    assertNoStoreHeaders(okRes);
    assert.equal(calls[0].url, "http://127.0.0.1:8000/api/v1/auth/register");
    const okJson = await okRes.json();
    assert.equal(okJson.email, "asha@example.com");
    assert.equal("access_token" in okJson, false);
    assert.equal("refresh_token" in okJson, false);

    const dupReq = makeBffRequest("http://localhost:3000/api/auth/register", {
      body: JSON.stringify({ email: "dup@example.com", password: secretPass }),
    });
    const dupRes = await handleRegister(dupReq, { fetchImpl: mockFetch, isProduction: false });
    assert.equal(dupRes.status, 400);
    const dupText = await dupRes.text();
    assert.match(dupText, /Email already registered/);
    assert.equal(dupText.includes(secretPass), false);
  });

  it("login stores refresh token only in HttpOnly cookie, calls /me, preserves Retry-After, and retains cookie on /me outage", async () => {
    const expSec = 1893456000;
    const accessJwt = makeJwtWithExp(expSec);
    assert.equal(extractAccessTokenExpiresAtMs(accessJwt), expSec * 1000);

    const refreshToken = "secret_refresh_token_login_1";
    const passwordUsed = "MyUltraSecretPass99!";

    // 1. Happy path
    const happyFetch = async (url, init) => {
      if (url.endsWith("/auth/login")) {
        return new Response(
          JSON.stringify({
            access_token: accessJwt,
            refresh_token: refreshToken,
            token_type: "bearer",
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      assert.equal(url, "http://127.0.0.1:8000/api/v1/me");
      assert.equal(init.headers.Authorization, `Bearer ${accessJwt}`);
      return new Response(JSON.stringify(SAMPLE_USER), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };

    const loginReq = makeBffRequest("http://localhost:3000/api/auth/login", {
      body: JSON.stringify({ email: "asha@example.com", password: passwordUsed }),
    });
    const loginRes = await handleLogin(loginReq, { fetchImpl: happyFetch, isProduction: false });
    assert.equal(loginRes.status, 200);
    assertNoStoreHeaders(loginRes);
    const setCookie = loginRes.headers.get("set-cookie") ?? "";
    assert.match(setCookie, new RegExp(`kundali_refresh_token=${refreshToken}`));
    assert.match(setCookie, /HttpOnly/);
    assert.match(setCookie, /SameSite=Lax/);
    assert.match(setCookie, /Path=\/api\/auth/);

    const loginText = await loginRes.text();
    assert.equal(loginText.includes(refreshToken), false);
    assert.equal(loginText.includes(passwordUsed), false);
    const loginData = JSON.parse(loginText);
    assert.equal(loginData.authenticated, true);
    assert.equal(loginData.access_token, accessJwt);
    assert.equal(loginData.expires_at, expSec * 1000);
    assert.equal(loginData.user.email, "asha@example.com");

    // 2. Rate-limited 429 preserves Retry-After
    const rateFetch = async () =>
      new Response(JSON.stringify({ detail: "Too many failed attempts. Please try again later." }), {
        status: 429,
        headers: { "content-type": "application/json", "retry-after": "42" },
      });
    const rateRes = await handleLogin(
      makeBffRequest("http://localhost:3000/api/auth/login", {
        body: JSON.stringify({ email: "asha@example.com", password: passwordUsed }),
      }),
      { fetchImpl: rateFetch, isProduction: false }
    );
    assert.equal(rateRes.status, 429);
    assert.equal(rateRes.headers.get("retry-after"), "42");
    assert.equal(rateRes.headers.get("set-cookie"), null);

    // 3. Login succeeds, /me fails temporarily -> MUST preserve valid refresh cookie
    const meFailFetch = async (url) => {
      if (url.endsWith("/auth/login")) {
        return new Response(
          JSON.stringify({ access_token: accessJwt, refresh_token: refreshToken }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      throw new TypeError("Upstream /me temporary connection error");
    };
    const meFailRes = await handleLogin(
      makeBffRequest("http://localhost:3000/api/auth/login", {
        body: JSON.stringify({ email: "asha@example.com", password: passwordUsed }),
      }),
      { fetchImpl: meFailFetch, isProduction: false }
    );
    assert.equal(meFailRes.status, 503);
    assertNoStoreHeaders(meFailRes);
    const preservedCookie = meFailRes.headers.get("set-cookie") ?? "";
    assert.match(preservedCookie, new RegExp(`kundali_refresh_token=${refreshToken}`));
    assert.equal((await meFailRes.json()).session_established, true);
  });
});

describe("BFF refresh rotation, error preservation, and revocation safety", () => {
  it("returns unauthenticated 200 with zero backend calls when refresh cookie is absent", async () => {
    let called = false;
    const req = makeBffRequest("http://localhost:3000/api/auth/refresh");
    const res = await handleRefresh(req, {
      fetchImpl: async () => {
        called = true;
        throw new Error("Should not call FastAPI without cookie");
      },
      isProduction: false,
    });
    assert.equal(called, false);
    assert.equal(res.status, 200);
    assertNoStoreHeaders(res);
    assert.equal(res.headers.get("set-cookie"), null);
    assert.deepEqual(await res.json(), {
      authenticated: false,
      access_token: null,
      expires_at: null,
      user: null,
    });
  });

  it("rotates refresh cookie and returns new access token + user without exposing refresh token in JSON", async () => {
    const oldRefresh = "old_refresh_token_1";
    const newRefresh = "rotated_refresh_token_2";
    const newAccess = makeJwtWithExp(1893459999);

    const req = makeBffRequest("http://localhost:3000/api/auth/refresh", {
      cookie: `kundali_refresh_token=${oldRefresh}`,
    });
    const res = await handleRefresh(req, {
      isProduction: true,
      frontendOrigin: "https://app.kundali.example",
      apiBaseUrl: "https://api.kundali.example/api/v1",
      fetchImpl: async () =>
        new Response("unused"),
    });
    // Expect CSRF reject above because origin header defaulted to http://localhost:3000; test exact match below:
    assert.equal(res.status, 403);

    const validReq = makeBffRequest("https://app.kundali.example/api/auth/refresh", {
      origin: "https://app.kundali.example",
      cookie: `kundali_refresh_token=${oldRefresh}`,
    });
    const okRes = await handleRefresh(validReq, {
      isProduction: true,
      frontendOrigin: "https://app.kundali.example",
      apiBaseUrl: "https://api.kundali.example/api/v1",
      fetchImpl: async (url, init) => {
        if (url.endsWith("/auth/refresh")) {
          assert.deepEqual(JSON.parse(init.body), { refresh_token: oldRefresh });
          return new Response(
            JSON.stringify({ access_token: newAccess, refresh_token: newRefresh }),
            { status: 200, headers: { "content-type": "application/json" } }
          );
        }
        assert.equal(url, "https://api.kundali.example/api/v1/me");
        return new Response(JSON.stringify(SAMPLE_USER), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      },
    });
    assert.equal(okRes.status, 200);
    assertNoStoreHeaders(okRes);
    const cookie = okRes.headers.get("set-cookie") ?? "";
    assert.match(cookie, new RegExp(`kundali_refresh_token=${newRefresh}`));
    assert.match(cookie, /Secure/);
    assert.equal(cookie.includes(oldRefresh), false);

    const text = await okRes.text();
    assert.equal(text.includes(oldRefresh), false);
    assert.equal(text.includes(newRefresh), false);
    const json = JSON.parse(text);
    assert.equal(json.authenticated, true);
    assert.equal(json.access_token, newAccess);
    assert.equal(json.user.id, SAMPLE_USER.id);
  });

  it("clears cookie on 401 invalid/revoked token, preserves cookie on temporary failure before rotation, and preserves replacement cookie if /me fails after rotation", async () => {
    const oldRefresh = "old_token_A";
    const replacementRefresh = "replacement_token_B";
    const newAccess = makeJwtWithExp(1893460000);

    // 1. Revoked / expired token -> clears cookie cleanly with 401
    const revokedRes = await handleRefresh(
      makeBffRequest("http://localhost:3000/api/auth/refresh", {
        cookie: `kundali_refresh_token=${oldRefresh}`,
      }),
      {
        isProduction: false,
        fetchImpl: async () =>
          new Response(JSON.stringify({ detail: "Invalid or expired refresh token" }), {
            status: 401,
            headers: { "content-type": "application/json" },
          }),
      }
    );
    assert.equal(revokedRes.status, 401);
    assertNoStoreHeaders(revokedRes);
    const clearedCookie = revokedRes.headers.get("set-cookie") ?? "";
    assert.match(clearedCookie, /Max-Age=0/);
    assert.match(clearedCookie, /Path=\/api\/auth/);

    // 2. Network/5xx BEFORE rotation -> MUST NOT clear existing cookie
    const preFailRes = await handleRefresh(
      makeBffRequest("http://localhost:3000/api/auth/refresh", {
        cookie: `kundali_refresh_token=${oldRefresh}`,
      }),
      {
        isProduction: false,
        fetchImpl: async () => {
          throw new TypeError("Connection refused");
        },
      }
    );
    assert.equal(preFailRes.status, 503);
    assertNoStoreHeaders(preFailRes);
    assert.equal(preFailRes.headers.get("set-cookie"), null);

    // 3. CRITICAL: Rotation succeeds (old token revoked), then /me fails temporarily ->
    // MUST return replacement token in Set-Cookie on the 503 error response!
    const postRotationMeFailRes = await handleRefresh(
      makeBffRequest("https://app.kundali.example/api/auth/refresh", {
        origin: "https://app.kundali.example",
        cookie: `kundali_refresh_token=${oldRefresh}`,
      }),
      {
        isProduction: true,
        frontendOrigin: "https://app.kundali.example",
        apiBaseUrl: "https://api.kundali.example/api/v1",
        fetchImpl: async (url) => {
          if (url.endsWith("/auth/refresh")) {
            return new Response(
              JSON.stringify({ access_token: newAccess, refresh_token: replacementRefresh }),
              { status: 200, headers: { "content-type": "application/json" } }
            );
          }
          return new Response(JSON.stringify({ detail: "Temporary upstream failure" }), {
            status: 503,
            headers: { "content-type": "application/json" },
          });
        },
      }
    );
    assert.equal(postRotationMeFailRes.status, 503);
    assertNoStoreHeaders(postRotationMeFailRes);
    const preservedReplacementCookie = postRotationMeFailRes.headers.get("set-cookie") ?? "";
    assert.match(
      preservedReplacementCookie,
      new RegExp(`kundali_refresh_token=${replacementRefresh}`)
    );
    assert.match(preservedReplacementCookie, /Max-Age=604800/);
    assert.match(preservedReplacementCookie, /HttpOnly/);
    assert.match(preservedReplacementCookie, /Secure/);
    const meFailBody = await postRotationMeFailRes.text();
    assert.equal(meFailBody.includes(replacementRefresh), false);
    assert.equal(JSON.parse(meFailBody).rotated, true);

    // 4. Rotation followed by /me 401 (e.g. account deactivated) clears cookie cleanly
    const postRotationMe401Res = await handleRefresh(
      makeBffRequest("http://localhost:3000/api/auth/refresh", {
        cookie: `kundali_refresh_token=${oldRefresh}`,
      }),
      {
        isProduction: false,
        fetchImpl: async (url) => {
          if (url.endsWith("/auth/refresh")) {
            return new Response(
              JSON.stringify({ access_token: newAccess, refresh_token: replacementRefresh }),
              { status: 200, headers: { "content-type": "application/json" } }
            );
          }
          return new Response(JSON.stringify({ detail: "Inactive user" }), {
            status: 401,
            headers: { "content-type": "application/json" },
          });
        },
      }
    );
    assert.equal(postRotationMe401Res.status, 401);
    assert.match(postRotationMe401Res.headers.get("set-cookie") ?? "", /Max-Age=0/);
  });
});

describe("BFF logout and logout-all routes", () => {
  it("logout calls backend when cookie present, always clears cookie, and reports revocation honestly", async () => {
    // 1. Confirmed backend revocation
    const okRes = await handleLogout(
      makeBffRequest("http://localhost:3000/api/auth/logout", {
        cookie: "kundali_refresh_token=revokable_tok",
      }),
      {
        isProduction: false,
        fetchImpl: async (url, init) => {
          assert.equal(url, "http://127.0.0.1:8000/api/v1/auth/logout");
          assert.deepEqual(JSON.parse(init.body), { refresh_token: "revokable_tok" });
          return new Response(null, { status: 204 });
        },
      }
    );
    assert.equal(okRes.status, 200);
    assertNoStoreHeaders(okRes);
    assert.match(okRes.headers.get("set-cookie") ?? "", /Max-Age=0/);
    assert.deepEqual(await okRes.json(), {
      local_cookie_cleared: true,
      backend_revoked: true,
    });

    // 2. Backend unavailable: still clears local cookie, never falsely reports backend revocation
    const downRes = await handleLogout(
      makeBffRequest("http://localhost:3000/api/auth/logout", {
        cookie: "kundali_refresh_token=revokable_tok",
      }),
      {
        isProduction: false,
        fetchImpl: async () => {
          throw new TypeError("Backend down");
        },
      }
    );
    assert.equal(downRes.status, 200);
    assert.match(downRes.headers.get("set-cookie") ?? "", /Max-Age=0/);
    assert.deepEqual(await downRes.json(), {
      local_cookie_cleared: true,
      backend_revoked: false,
      reason: "backend_unconfirmed",
    });

    // 3. Missing cookie: no backend call, clears cookie idempotently
    let called = false;
    const missingRes = await handleLogout(makeBffRequest("http://localhost:3000/api/auth/logout"), {
      isProduction: false,
      fetchImpl: async () => {
        called = true;
        return new Response(null, { status: 204 });
      },
    });
    assert.equal(called, false);
    assert.equal(missingRes.status, 200);
    assert.match(missingRes.headers.get("set-cookie") ?? "", /Max-Age=0/);
    assert.deepEqual(await missingRes.json(), {
      local_cookie_cleared: true,
      backend_revoked: false,
      reason: "missing_cookie",
    });
  });

  it("logout-all requires valid Bearer token, forwards it, clears cookie only on confirmed completion, and preserves 401/503 honesty", async () => {
    // 1. Missing Bearer token rejected before fetch
    let called = false;
    const noAuthRes = await handleLogoutAll(
      makeBffRequest("http://localhost:3000/api/auth/logout-all"),
      {
        isProduction: false,
        fetchImpl: async () => {
          called = true;
          return new Response(null, { status: 204 });
        },
      }
    );
    assert.equal(called, false);
    assert.equal(noAuthRes.status, 401);
    assert.equal(noAuthRes.headers.get("set-cookie"), null);
    assert.equal((await noAuthRes.json()).backend_revoked, false);

    // 2. Stale access token returns 401 without clearing refresh cookie (allowing Commit 2 refresh)
    const staleRes = await handleLogoutAll(
      makeBffRequest("http://localhost:3000/api/auth/logout-all", {
        headers: { authorization: "Bearer stale_token" },
        cookie: "kundali_refresh_token=keep_me_until_refresh",
      }),
      {
        isProduction: false,
        fetchImpl: async () =>
          new Response(JSON.stringify({ detail: "Expired" }), {
            status: 401,
            headers: { "content-type": "application/json" },
          }),
      }
    );
    assert.equal(staleRes.status, 401);
    assert.equal(staleRes.headers.get("set-cookie"), null);
    const staleJson = await staleRes.json();
    assert.equal(staleJson.backend_revoked, false);
    assert.equal(staleJson.local_cookie_cleared, false);

    // 3. Backend unavailable returns 503 with honest unrevoked status
    const downRes = await handleLogoutAll(
      makeBffRequest("http://localhost:3000/api/auth/logout-all", {
        headers: { authorization: "Bearer valid_token" },
      }),
      {
        isProduction: false,
        fetchImpl: async () => {
          throw new TypeError("Offline");
        },
      }
    );
    assert.equal(downRes.status, 503);
    assert.equal((await downRes.json()).backend_revoked, false);

    // 4. Success clears local refresh cookie and reports confirmed revocation
    const okRes = await handleLogoutAll(
      makeBffRequest("http://localhost:3000/api/auth/logout-all", {
        headers: { authorization: "Bearer valid_token" },
        cookie: "kundali_refresh_token=active_refresh",
      }),
      {
        isProduction: false,
        fetchImpl: async (url, init) => {
          assert.equal(url, "http://127.0.0.1:8000/api/v1/auth/logout-all");
          assert.equal(init.headers.Authorization, "Bearer valid_token");
          return new Response(null, { status: 204 });
        },
      }
    );
    assert.equal(okRes.status, 200);
    assertNoStoreHeaders(okRes);
    assert.match(okRes.headers.get("set-cookie") ?? "", /Max-Age=0/);
    assert.deepEqual(await okRes.json(), {
      local_cookie_cleared: true,
      backend_revoked: true,
    });
  });
});

describe("Route handler entrypoints wiring", () => {
  it("exposes working POST handlers on all five /api/auth/* route files", async () => {
    const originalFetch = globalThis.fetch;
    const accessJwt = makeJwtWithExp(1893470000);
    globalThis.fetch = async (url) => {
      const target = String(url);
      if (target.endsWith("/auth/register")) {
        return new Response(JSON.stringify(SAMPLE_USER), {
          status: 201,
          headers: { "content-type": "application/json" },
        });
      }
      if (target.endsWith("/auth/login") || target.endsWith("/auth/refresh")) {
        return new Response(
          JSON.stringify({ access_token: accessJwt, refresh_token: "route_refresh_tok" }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      if (target.endsWith("/me")) {
        return new Response(JSON.stringify(SAMPLE_USER), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(null, { status: 204 });
    };

    try {
      const rReg = await registerRoutePost(
        makeBffRequest("http://localhost:3000/api/auth/register", {
          body: JSON.stringify({ email: "asha@example.com", password: "ValidPassword2026!" }),
        })
      );
      assert.equal(rReg.status, 201);
      assertNoStoreHeaders(rReg);

      const rLogin = await loginRoutePost(
        makeBffRequest("http://localhost:3000/api/auth/login", {
          body: JSON.stringify({ email: "asha@example.com", password: "ValidPassword2026!" }),
        })
      );
      assert.equal(rLogin.status, 200);
      assert.match(rLogin.headers.get("set-cookie") ?? "", /route_refresh_tok/);

      const rRefresh = await refreshRoutePost(
        makeBffRequest("http://localhost:3000/api/auth/refresh", {
          cookie: "kundali_refresh_token=route_refresh_tok",
        })
      );
      assert.equal(rRefresh.status, 200);
      assertNoStoreHeaders(rRefresh);

      const rLogout = await logoutRoutePost(
        makeBffRequest("http://localhost:3000/api/auth/logout", {
          cookie: "kundali_refresh_token=route_refresh_tok",
        })
      );
      assert.equal(rLogout.status, 200);
      assert.match(rLogout.headers.get("set-cookie") ?? "", /Max-Age=0/);

      const rLogoutAll = await logoutAllRoutePost(
        makeBffRequest("http://localhost:3000/api/auth/logout-all", {
          headers: { authorization: `Bearer ${accessJwt}` },
          cookie: "kundali_refresh_token=route_refresh_tok",
        })
      );
      assert.equal(rLogoutAll.status, 200);
      assert.match(rLogoutAll.headers.get("set-cookie") ?? "", /Max-Age=0/);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
