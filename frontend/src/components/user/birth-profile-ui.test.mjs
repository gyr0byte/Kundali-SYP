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
const { AuthSessionProvider } = await import("../auth/AuthSessionProvider.tsx");
const {
  classifyWorkspaceAuthError,
  fetchWorkspaceProfilesSafely,
  reconcileWorkspaceSessionTransition,
} = await import("../../lib/kundali/profile-workflow.ts");
const { BirthProfileForm } = await import("./BirthProfileForm.tsx");
const { UserChartWorkspace } = await import("./UserChartWorkspace.tsx");

const t = enMessages.userWorkspace;

const formLabels = {
  formTitle: t.formTitle,
  editFormTitle: t.editFormTitle,
  formSubtitle: t.formSubtitle,
  authFormLockedNotice: t.authFormLockedNotice,
  formLabel: t.formLabel,
  formLabelPlaceholder: t.formLabelPlaceholder,
  formInputCalendar: t.formInputCalendar,
  formDate: t.formDate,
  formCertainty: t.formCertainty,
  formTime: t.formTime,
  formTimeUnknownNote: t.formTimeUnknownNote,
  formPlace: t.formPlace,
  formPlacePlaceholder: t.formPlacePlaceholder,
  formTimezone: t.formTimezone,
  formTimezonePlaceholder: t.formTimezonePlaceholder,
  formLatitude: t.formLatitude,
  formLongitude: t.formLongitude,
  formLatitudePlaceholder: t.formLatitudePlaceholder,
  formLongitudePlaceholder: t.formLongitudePlaceholder,
  formCoordinatesNote: t.formCoordinatesNote,
  formSubmit: t.formSubmit,
  editFormSubmit: t.editFormSubmit,
  formSaving: t.formSaving,
  formCancel: t.formCancel,
  loadSampleButton: t.loadSampleButton,
  timeExact: t.timeExact,
  timeApproximate: t.timeApproximate,
  timeUnknown: t.timeUnknown,
};

describe("BirthProfileForm and UserChartWorkspace rendered UI states", () => {
  it("renders unauthenticated state cleanly with disabled save and no prefilled Kathmandu values", () => {
    const html = renderToStaticMarkup(
      React.createElement(UserChartWorkspace, {
        messagesByLocale: { en: enMessages.userWorkspace, ne: neMessages.userWorkspace },
      })
    );

    assert.match(html, /Authentication Required to Manage Saved Profiles/);
    assert.match(html, /Preview Synthetic Sample \(London, 2015\)/);
    assert.match(html, /type="submit" disabled=""[^>]*>Save Profile/);
    assert.equal(html.includes('value="Kathmandu, Nepal"'), false);
    assert.equal(html.includes('value="27.7172"'), false);
    assert.equal(html.includes('value="85.3240"'), false);
    assert.equal(html.includes('value="2055-04-15"'), false);
  });

  it("renders authenticated create mode with blank explicit fields and server error alerts", () => {
    const html = renderToStaticMarkup(
      React.createElement(BirthProfileForm, {
        mode: "create",
        canCancel: true,
        isAuthenticated: true,
        serverErrors: ["Timezone must be a valid region-based IANA identifier or UTC"],
        onSubmitProfile: () => {},
        onLoadSyntheticSample: () => {},
        onCancel: () => {},
        labels: formLabels,
      })
    );

    assert.match(html, />Create Birth Profile</);
    assert.match(html, /type="submit"[^>]*>Save Profile</);
    assert.equal(html.includes('type="submit" disabled=""'), false);
    assert.match(html, /role="alert"[^>]*>.*Timezone must be a valid region-based IANA identifier or UTC/);
  });

  it("renders edit mode prefilled cleanly from saved BS unknown-time profile", () => {
    const html = renderToStaticMarkup(
      React.createElement(BirthProfileForm, {
        mode: "edit",
        canCancel: true,
        isAuthenticated: true,
        initialProfile: {
          id: "prof-edit-1",
          label: "Ramesh Pokhara",
          input_calendar: "BS",
          entered_date: "2055-04-15",
          date_ad: null,
          bs_conversion_status: "awaiting_bs_conversion",
          time_certainty: "unknown",
          time_local: null,
          place_name: "Pokhara, Nepal",
          latitude: 28.2096,
          longitude: 83.9856,
          timezone: "Asia/Kathmandu",
          is_synthetic_sample: false,
        },
        onSubmitProfile: () => {},
        onLoadSyntheticSample: () => {},
        onCancel: () => {},
        labels: formLabels,
      })
    );

    assert.match(html, />Edit Birth Profile</);
    assert.match(html, />Update Profile</);
    assert.match(html, /value="Ramesh Pokhara"/);
    assert.match(html, /value="2055-04-15"/);
    assert.match(html, /value="Pokhara, Nepal"/);
    assert.match(html, /value="28\.2096"/);
    assert.match(html, /value="83\.9856"/);
    assert.match(html, /id="bp-time"[^>]*disabled=""/);
  });

  it("renders AuthSessionProvider + UserChartWorkspace session checking, unavailable, and authenticated states cleanly", () => {
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

    const baseMessages = { en: enMessages.userWorkspace, ne: neMessages.userWorkspace };

    // 1. Checking state avoids premature "Authentication Required" alarm
    const checkingHtml = renderToStaticMarkup(
      React.createElement(
        AuthSessionProvider,
        { manager: createStubManager({ status: "checking", user: null, isAuthenticated: false, error: null, hasRecoverableSession: false }) },
        React.createElement(UserChartWorkspace, { messagesByLocale: baseMessages })
      )
    );
    assert.equal(checkingHtml.includes("Authentication Required to Manage Saved Profiles"), false);
    assert.equal(checkingHtml.includes("Session Service Temporarily Unavailable"), false);

    // 2. Unavailable state renders recoverable retry alert cleanly
    const unavailableHtml = renderToStaticMarkup(
      React.createElement(
        AuthSessionProvider,
        {
          manager: createStubManager({
            status: "unavailable",
            user: {
              id: "u1",
              email: "asha@example.com",
              role: "user",
              language: "ne",
              is_active: true,
              created_at: "2026-11-25T10:00:00Z",
            },
            isAuthenticated: false,
            error: {
              code: "BACKEND_UNAVAILABLE",
              status: 503,
              message: "Backend session verification temporarily unreachable.",
              retryable: true,
            },
            hasRecoverableSession: true,
          }),
        },
        React.createElement(UserChartWorkspace, { messagesByLocale: baseMessages })
      )
    );
    assert.match(unavailableHtml, /Session Service Temporarily Unavailable/);
    assert.match(unavailableHtml, /Retry Session/);
    assert.equal(unavailableHtml.includes("Authentication Required to Manage Saved Profiles"), false);

    // 3. Authenticated state enables profile creation
    const authedHtml = renderToStaticMarkup(
      React.createElement(
        AuthSessionProvider,
        {
          manager: createStubManager({
            status: "authenticated",
            user: {
              id: "u1",
              email: "asha@example.com",
              role: "user",
              language: "ne",
              is_active: true,
              created_at: "2026-11-25T10:00:00Z",
            },
            isAuthenticated: true,
            error: null,
            hasRecoverableSession: true,
          }),
        },
        React.createElement(UserChartWorkspace, { messagesByLocale: baseMessages })
      )
    );
    assert.equal(authedHtml.includes("Authentication Required to Manage Saved Profiles"), false);
    assert.match(authedHtml, /type="submit"[^>]*>Save Profile/);
  });

  it("handles rejected getAccessToken, AUTH_REQUIRED delete errors, and checking/unavailable/unauthenticated transitions safely", async () => {
    // 1. Transition guard prevents fetches during checking, unavailable, and unauthenticated
    assert.equal(
      reconcileWorkspaceSessionTransition({
        sessionStatus: "checking",
        userId: null,
        loadedOwnerKey: null,
      }),
      "wait"
    );
    assert.equal(
      reconcileWorkspaceSessionTransition({
        sessionStatus: "unavailable",
        userId: "u1",
        loadedOwnerKey: "u1",
      }),
      "preserve"
    );
    assert.equal(
      reconcileWorkspaceSessionTransition({
        sessionStatus: "unauthenticated",
        userId: null,
        loadedOwnerKey: "u1",
      }),
      "clear"
    );
    assert.equal(
      reconcileWorkspaceSessionTransition({
        sessionStatus: "authenticated",
        userId: "u1",
        loadedOwnerKey: "u1",
      }),
      "noop"
    );
    assert.equal(
      reconcileWorkspaceSessionTransition({
        sessionStatus: "authenticated",
        userId: "u1",
        loadedOwnerKey: null,
      }),
      "fetch"
    );

    // 2. AUTH_REQUIRED & UNAUTHORIZED preserve form/profiles during transient session unavailability,
    // and clear cleanly during definitive unauthenticated transitions (including delete handler!)
    assert.equal(
      classifyWorkspaceAuthError({
        errorCode: "AUTH_REQUIRED",
        liveSessionStatus: "unauthenticated",
      }),
      "unauthenticated"
    );
    assert.equal(
      classifyWorkspaceAuthError({
        errorCode: "UNAUTHORIZED",
        liveSessionStatus: "unavailable",
      }),
      "unavailable"
    );

    // 3. Rejected getAccessToken() promise is caught cleanly inside fetchWorkspaceProfilesSafely
    let fetchAttempted = false;
    const rejectedResult = await fetchWorkspaceProfilesSafely({
      getAccessToken: async () => {
        throw new Error("Session provider failed unexpectedly");
      },
      fetchList: async () => {
        fetchAttempted = true;
        return [];
      },
      unavailableFallbackMessage: "Retry later",
    });
    assert.equal(fetchAttempted, false);
    assert.equal(rejectedResult.kind, "error");
    assert.match(rejectedResult.message, /Session provider failed unexpectedly/);
  });
});
