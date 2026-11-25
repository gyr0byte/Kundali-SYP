import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(__dirname, "../..");

const NEXT_LINK_STUB_URL = pathToFileURL(path.join(SRC_ROOT, "__virtual_next_link_stub__.mjs")).href;

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "server-only") {
      return {
        url: "data:text/javascript,export default {};",
        shortCircuit: true,
      };
    }
    if (specifier === "next/link") {
      return {
        url: NEXT_LINK_STUB_URL,
        shortCircuit: true,
      };
    }
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
    if (url === NEXT_LINK_STUB_URL) {
      return {
        format: "module",
        shortCircuit: true,
        source:
          "import React from 'react'; export default function Link({href, children, ...rest}){ return React.createElement('a', {href: typeof href === 'string' ? href : String(href), ...rest}, children); }",
      };
    }
    if (url.startsWith("file:") && (url.endsWith(".tsx") || url.endsWith(".ts"))) {
      const source = readFileSync(fileURLToPath(url), "utf8");
      const transpiled = ts.transpileModule(source, {
        fileName: fileURLToPath(url),
        compilerOptions: {
          module: ts.ModuleKind.ESNext,
          target: ts.ScriptTarget.ES2022,
          jsx: ts.JsxEmit.ReactJSX,
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

const React = await import("react");
const { renderToStaticMarkup } = await import("react-dom/server");
const enMessages = JSON.parse(readFileSync(path.join(SRC_ROOT, "i18n/en.json"), "utf8"));
const neMessages = JSON.parse(readFileSync(path.join(SRC_ROOT, "i18n/ne.json"), "utf8"));

const { AuthSessionProvider } = await import("./AuthSessionProvider.tsx");
const { LoginForm } = await import("./LoginForm.tsx");
const { RegisterForm } = await import("./RegisterForm.tsx");
const {
  resolveSafePostLoginRedirect,
  validateLoginInputs,
  validateRegistrationInputs,
} = await import("../../lib/auth/navigation.ts");
const {
  classifyLogoutAllOutcome,
  classifyLogoutOutcome,
  resolveLocalizedAuthErrors,
} = await import("../../lib/auth/ui-helpers.ts");

function createStubManager(snapshot) {
  return {
    getSnapshot: () => snapshot,
    subscribe: () => () => {},
    bootstrap: async () => snapshot,
    getAccessToken: async () => (snapshot.isAuthenticated ? "tok" : null),
    refreshSession: async () => null,
    refreshOnUnauthorized: async () => null,
    retrySession: async () => snapshot,
    register: async () => ({ ok: false, status: 500 }),
    login: async () => ({ ok: false, status: 500 }),
    logout: async () => ({
      localCookieCleared: true,
      backendLogoutRequestCompleted: true,
      backendRevocationState: "logout_request_accepted",
    }),
    logoutAll: async () => ({
      ok: false,
      status: 401,
      localCookieCleared: false,
      backendLogoutRequestCompleted: false,
      backendRevocationState: "unauthenticated",
    }),
    dispose() {},
  };
}

describe("Post-login redirect validation and form input rules", () => {
  it("allows only safe internal destinations and rejects external, protocol-relative, backslash, and encoded bypass URLs", () => {
    assert.equal(resolveSafePostLoginRedirect(null), "/user");
    assert.equal(resolveSafePostLoginRedirect(""), "/user");
    assert.equal(resolveSafePostLoginRedirect("/user"), "/user");
    assert.equal(resolveSafePostLoginRedirect("/admin"), "/admin");
    assert.equal(resolveSafePostLoginRedirect("/astrologer"), "/astrologer");
    assert.equal(resolveSafePostLoginRedirect("/"), "/");
    assert.equal(resolveSafePostLoginRedirect("/user?tab=dasha#summary"), "/user?tab=dasha#summary");

    const unsafe = [
      "https://evil.example/user",
      "http://127.0.0.1:8000/user",
      "//evil.example",
      "//evil.example/user",
      "/\\evil.example",
      "/user\\..\\secret",
      "/%2f%2fevil.example",
      "/%5cevil.example",
      "/user%0d%0aSet-Cookie:evil=1",
      "javascript:alert(1)",
      "/login",
      "/register",
      "/api/auth/logout",
      "/unknown-path",
      "/%ZZ-malformed",
    ];
    for (const candidate of unsafe) {
      assert.equal(resolveSafePostLoginRedirect(candidate), "/user", `Failed to reject ${candidate}`);
    }
  });

  it("enforces login email/password checks and registration 10..128 + confirmation rules without fake strength meters", () => {
    assert.equal(validateLoginInputs("invalid-email", "secret").errorKey, "emailInvalid");
    assert.equal(validateLoginInputs("asha@example.com", "").errorKey, "passwordRequired");
    assert.deepEqual(validateLoginInputs("  asha@example.com ", "ValidPass123!"), {
      email: "asha@example.com",
      errorKey: null,
    });

    assert.equal(
      validateRegistrationInputs("bad", "LongEnough10!", "LongEnough10!").errorKey,
      "emailInvalid"
    );
    assert.equal(
      validateRegistrationInputs("asha@example.com", "short9", "short9").errorKey,
      "passwordTooShort"
    );
    const overMax = "a".repeat(129);
    assert.equal(
      validateRegistrationInputs("asha@example.com", overMax, overMax).errorKey,
      "passwordTooLong"
    );
    assert.equal(
      validateRegistrationInputs("asha@example.com", "ValidPass123!", "Mismatch123!").errorKey,
      "passwordMismatch"
    );
    assert.deepEqual(
      validateRegistrationInputs(" asha@example.com ", "ValidPass123!", "ValidPass123!"),
      {
        email: "asha@example.com",
        errorKey: null,
      }
    );
  });
});

describe("Bilingual i18n coverage, error classification, and logout truthfulness", () => {
  it("keeps EN and NE auth and userWorkspace message keys in complete parity", () => {
    assert.deepEqual(Object.keys(enMessages.auth).sort(), Object.keys(neMessages.auth).sort());
    assert.deepEqual(
      Object.keys(enMessages.userWorkspace).sort(),
      Object.keys(neMessages.userWorkspace).sort()
    );
  });

  it("maps 401, 429 Retry-After, 422, 400 duplicate email, 503, and SESSION_RECOVERY_UNAVAILABLE in EN and NE", () => {
    for (const locale of ["en", "ne"]) {
      const t = (locale === "en" ? enMessages : neMessages).auth;
      assert.deepEqual(resolveLocalizedAuthErrors({ ok: false, status: 401, code: "INVALID_CREDENTIALS" }, t), [
        t.errorInvalidCredentials,
      ]);
      assert.deepEqual(
        resolveLocalizedAuthErrors(
          { ok: false, status: 429, code: "RATE_LIMITED", retryAfter: "45", retryAfterSeconds: 45 },
          t
        ),
        [t.errorRateLimitedWithSeconds.replace("{seconds}", "45")]
      );
      assert.deepEqual(
        resolveLocalizedAuthErrors(
          { ok: false, status: 429, code: "RATE_LIMITED", retryAfter: null, retryAfterSeconds: null },
          t
        ),
        [t.errorRateLimitedNoDelay]
      );
      assert.deepEqual(
        resolveLocalizedAuthErrors(
          { ok: false, status: 400, code: "REGISTRATION_REJECTED", message: "Email already registered." },
          t
        ),
        [t.errorDuplicateEmail]
      );
      assert.deepEqual(
        resolveLocalizedAuthErrors(
          { ok: false, status: 422, code: "VALIDATION_ERROR", validationMessages: ["Password too weak"] },
          t
        ),
        ["Password too weak"]
      );
      assert.deepEqual(
        resolveLocalizedAuthErrors({ ok: false, status: 503, code: "BACKEND_UNAVAILABLE" }, t),
        [t.errorBackendUnavailable]
      );
      assert.deepEqual(
        resolveLocalizedAuthErrors(
          { ok: false, status: 503, code: "SESSION_RECOVERY_UNAVAILABLE", sessionEstablished: true },
          t
        ),
        [t.errorSessionRecovery]
      );
    }
  });

  it("distinguishes confirmed vs unconfirmed vs network logout outcomes accurately", () => {
    const t = enMessages.userWorkspace;
    assert.deepEqual(
      classifyLogoutOutcome(
        {
          localCookieCleared: true,
          backendLogoutRequestCompleted: true,
          backendRevocationState: "logout_request_accepted",
        },
        t
      ),
      { tone: "emerald", message: t.logoutOutcomeConfirmed }
    );
    assert.deepEqual(
      classifyLogoutOutcome(
        {
          localCookieCleared: true,
          backendLogoutRequestCompleted: false,
          backendRevocationState: "backend_unconfirmed",
        },
        t
      ),
      { tone: "amber", message: t.logoutOutcomeUnconfirmed }
    );
    assert.deepEqual(
      classifyLogoutOutcome(
        {
          localCookieCleared: false,
          backendLogoutRequestCompleted: false,
          backendRevocationState: "network_error",
        },
        t
      ),
      { tone: "crimson", message: t.logoutOutcomeNetworkError }
    );

    assert.deepEqual(
      classifyLogoutAllOutcome(
        {
          ok: true,
          status: 200,
          localCookieCleared: true,
          backendLogoutRequestCompleted: true,
          backendRevocationState: "all_refresh_tokens_revoked",
        },
        t
      ),
      { tone: "emerald", message: t.logoutAllConfirmedNotice }
    );
    const failedAll = classifyLogoutAllOutcome(
      {
        ok: false,
        status: 503,
        localCookieCleared: false,
        backendLogoutRequestCompleted: false,
        backendRevocationState: "backend_unconfirmed",
        message: "Service offline",
      },
      t
    );
    assert.equal(failedAll.tone, "crimson");
    assert.match(failedAll.message, /Service offline/);
  });
});

describe("LoginForm and RegisterForm accessible SSR rendering across session states", () => {
  const authMessages = { en: enMessages.auth, ne: neMessages.auth };

  it("renders checking, unavailable-with-retry, and registered EN/NE login views cleanly without premature forms or cosmic clichés", () => {
    const checkingHtml = renderToStaticMarkup(
      React.createElement(
        AuthSessionProvider,
        {
          manager: createStubManager({
            status: "checking",
            user: null,
            isAuthenticated: false,
            error: null,
            hasRecoverableSession: false,
          }),
        },
        React.createElement(LoginForm, { messagesByLocale: authMessages })
      )
    );
    assert.match(checkingHtml, /Verifying your session/);
    assert.equal(checkingHtml.includes('id="login-email"'), false);

    const unavailableHtml = renderToStaticMarkup(
      React.createElement(
        AuthSessionProvider,
        {
          manager: createStubManager({
            status: "unavailable",
            user: null,
            isAuthenticated: false,
            error: {
              code: "BACKEND_UNAVAILABLE",
              status: 503,
              message: "Temporary failure",
              retryable: true,
            },
            hasRecoverableSession: true,
          }),
        },
        React.createElement(LoginForm, { messagesByLocale: authMessages })
      )
    );
    assert.match(unavailableHtml, /Retry session/);
    assert.match(unavailableHtml, /sign-in session cookie was stored/);

    const unauthEnHtml = renderToStaticMarkup(
      React.createElement(
        AuthSessionProvider,
        {
          manager: createStubManager({
            status: "unauthenticated",
            user: null,
            isAuthenticated: false,
            error: null,
            hasRecoverableSession: false,
          }),
        },
        React.createElement(LoginForm, {
          messagesByLocale: authMessages,
          registeredParam: "1",
        })
      )
    );
    assert.match(unauthEnHtml, /Account created successfully/);
    assert.match(unauthEnHtml, /for="login-email"/);
    assert.match(unauthEnHtml, /autoComplete="email"/i);
    assert.match(unauthEnHtml, /for="login-password"/);
    assert.match(unauthEnHtml, /autoComplete="current-password"/i);
    assert.match(unauthEnHtml, /href="\/register"/);

    const unauthNeHtml = renderToStaticMarkup(
      React.createElement(
        AuthSessionProvider,
        {
          manager: createStubManager({
            status: "unauthenticated",
            user: null,
            isAuthenticated: false,
            error: null,
            hasRecoverableSession: false,
          }),
        },
        React.createElement(LoginForm, {
          messagesByLocale: authMessages,
          initialLocale: "ne",
        })
      )
    );
    assert.match(unauthNeHtml, /साइन इन गर्नुहोस्/);
    assert.match(unauthNeHtml, /lang="ne"/);
  });

  it("renders RegisterForm with explicit email, password, confirm-password labels, 10..128 limits, and Nepali support", () => {
    const regEnHtml = renderToStaticMarkup(
      React.createElement(
        AuthSessionProvider,
        {
          manager: createStubManager({
            status: "unauthenticated",
            user: null,
            isAuthenticated: false,
            error: null,
            hasRecoverableSession: false,
          }),
        },
        React.createElement(RegisterForm, { messagesByLocale: authMessages })
      )
    );
    assert.match(regEnHtml, /for="register-email"/);
    assert.match(regEnHtml, /for="register-password"/);
    assert.match(regEnHtml, /for="register-confirm-password"/);
    assert.match(regEnHtml, /minLength="10"/i);
    assert.match(regEnHtml, /maxLength="128"/i);
    assert.match(regEnHtml, /autoComplete="new-password"/i);
    assert.match(regEnHtml, /10 to 128 characters/);
    assert.match(regEnHtml, /href="\/login"/);

    const regNeHtml = renderToStaticMarkup(
      React.createElement(
        AuthSessionProvider,
        {
          manager: createStubManager({
            status: "unauthenticated",
            user: null,
            isAuthenticated: false,
            error: null,
            hasRecoverableSession: false,
          }),
        },
        React.createElement(RegisterForm, {
          messagesByLocale: authMessages,
          initialLocale: "ne",
        })
      )
    );
    assert.match(regNeHtml, /खाता सिर्जना गर्नुहोस्/);
    assert.match(regNeHtml, /पासवर्ड पुष्टि गर्नुहोस्/);
  });
});
