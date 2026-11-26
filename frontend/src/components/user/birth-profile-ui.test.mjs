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
const { AuthSessionProvider } = await import("../auth/AuthSessionProvider.tsx");
const {
  activateSyntheticSamplePreview,
  applyLoadedProfiles,
  applySessionCleared,
  classifyWorkspaceAuthError,
  createInitialWorkspaceState,
  createProfileLoadCoordinator,
  fetchWorkspaceProfilesSafely,
  reconcileWorkspaceSessionTransition,
  resolveActiveProfile,
  resolveVisibleProfiles,
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
  it("renders the signed-out workspace with auth and sample entry points", () => {
    const html = renderToStaticMarkup(
      React.createElement(UserChartWorkspace, {
        messagesByLocale: { en: enMessages.userWorkspace, ne: neMessages.userWorkspace },
      })
    );

    assert.match(html, /Authentication Required to Manage Saved Profiles/);
    assert.match(html, /href="\/login"/);
    assert.match(html, /href="\/register"/);
    assert.match(html, /Explore a sample chart/);
    assert.doesNotMatch(html, />Save Profile</);
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
    assert.match(checkingHtml, /Checking session/);
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
    assert.match(unavailableHtml, /Retry [Ss]ession/);
    assert.match(unavailableHtml, /asha@example\.com/);
    assert.equal(unavailableHtml.includes("Authentication Required to Manage Saved Profiles"), false);

    // 3. Authenticated state enables profile creation and displays identity + sign-out controls
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
    assert.match(authedHtml, /asha@example\.com/);
    assert.match(authedHtml, /Role:.*user/);
    assert.match(authedHtml, />Sign out</);
    assert.match(authedHtml, />Sign out all devices</);
    assert.match(authedHtml, /Start with a birth profile/);
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

  it("ignores delayed User A profile responses after logout and User B switch without clearing User B loading indicator", async () => {
    const coordinator = createProfileLoadCoordinator();
    let workspaceState = createInitialWorkspaceState();
    let liveSession = { status: "authenticated", ownerKey: "user-A" };
    let isLoading = false;
    const errors = [];

    const userAProfile = {
      id: "prof-a-1",
      label: "User A Secret Profile",
      input_calendar: "AD",
      entered_date: "1990-01-01",
      date_ad: "1990-01-01",
      bs_conversion_status: "resolved",
      time_certainty: "exact",
      time_local: "09:00",
      place_name: "Kathmandu",
      latitude: 27.7172,
      longitude: 85.324,
      timezone: "Asia/Kathmandu",
      is_synthetic_sample: false,
    };
    const userBProfile = {
      ...userAProfile,
      id: "prof-b-1",
      label: "User B Chart",
      place_name: "Pokhara",
    };

    let releaseUserAFetch;
    const userAFetchDeferred = new Promise((res) => {
      releaseUserAFetch = res;
    });
    let releaseUserBFetch;
    const userBFetchDeferred = new Promise((res) => {
      releaseUserBFetch = res;
    });

    // 1. User A begins delayed profile-list request
    coordinator.syncSessionContext({ status: "authenticated", ownerKey: "user-A" });
    const reqAPromise = coordinator.startLoad({
      ownerKey: "user-A",
      getAccessToken: () => "tok-A",
      getLiveContext: () => liveSession,
      unavailableFallbackMessage: "Unavailable",
      fetchList: async () => userAFetchDeferred,
      onLoadingChange: (v) => {
        isLoading = v;
      },
      onLoaded: (items) => {
        workspaceState = applyLoadedProfiles(workspaceState, items);
      },
      onUnauthenticated: () => {
        errors.push("unauth-A");
      },
      onUnavailable: (msg) => {
        errors.push(`unavail-A:${msg}`);
      },
      onError: (msg) => {
        errors.push(`err-A:${msg}`);
      },
    });
    await new Promise((r) => setTimeout(r, 5));
    assert.equal(isLoading, true);

    // 2. User A logs out
    liveSession = { status: "unauthenticated", ownerKey: null };
    const logoutTransition = coordinator.syncSessionContext({
      status: "unauthenticated",
      ownerKey: null,
    });
    assert.equal(logoutTransition.shouldClearWorkspace, true);
    assert.equal(logoutTransition.shouldFetch, false);
    workspaceState = applySessionCleared(workspaceState);
    isLoading = false;

    // 3. User B authenticates and begins profile request
    liveSession = { status: "authenticated", ownerKey: "user-B" };
    const loginBTransition = coordinator.syncSessionContext({
      status: "authenticated",
      ownerKey: "user-B",
    });
    assert.equal(loginBTransition.shouldFetch, true);
    const reqBPromise = coordinator.startLoad({
      ownerKey: "user-B",
      getAccessToken: () => "tok-B",
      getLiveContext: () => liveSession,
      unavailableFallbackMessage: "Unavailable",
      fetchList: async () => userBFetchDeferred,
      onLoadingChange: (v) => {
        isLoading = v;
      },
      onLoaded: (items) => {
        workspaceState = applyLoadedProfiles(workspaceState, items);
      },
      onUnauthenticated: () => {
        errors.push("unauth-B");
      },
      onUnavailable: (msg) => {
        errors.push(`unavail-B:${msg}`);
      },
      onError: (msg) => {
        errors.push(`err-B:${msg}`);
      },
    });
    await new Promise((r) => setTimeout(r, 5));
    assert.equal(isLoading, true);

    // 4. First test loading-indicator protection: if User A's delayed request resolves while User B
    // is still loading, it MUST NOT apply User A's data OR clear User B's loading indicator!
    releaseUserAFetch([userAProfile]);
    await reqAPromise;
    assert.equal(isLoading, true);
    assert.equal(workspaceState.savedProfiles.length, 0);

    // 5. User B completes -> User B's profiles become active and loading ends cleanly
    releaseUserBFetch([userBProfile]);
    await reqBPromise;
    assert.equal(isLoading, false);
    assert.deepEqual(workspaceState.savedProfiles.map((p) => p.id), ["prof-b-1"]);
    assert.equal(resolveActiveProfile(workspaceState)?.id, "prof-b-1");
    assert.equal(coordinator.getSnapshot().loadedOwnerKey, "user-B");
    assert.deepEqual(errors, []);

    // 6. Exact sequence where User B completes BEFORE User A's delayed response arrives:
    // User C (or User A again) starts delayed load -> logs out -> User B loads & completes -> delayed arrives AFTERWARD
    let releaseDelayedFirst;
    const delayedFirst = new Promise((res) => {
      releaseDelayedFirst = res;
    });
    let releaseSecond;
    const secondFetch = new Promise((res) => {
      releaseSecond = res;
    });

    const c2 = createProfileLoadCoordinator();
    let state2 = createInitialWorkspaceState();
    let live2 = { status: "authenticated", ownerKey: "user-A" };

    c2.syncSessionContext({ status: "authenticated", ownerKey: "user-A" });
    const delayedReq = c2.startLoad({
      ownerKey: "user-A",
      getAccessToken: () => "tok-A2",
      getLiveContext: () => live2,
      unavailableFallbackMessage: "Unavailable",
      fetchList: async () => delayedFirst,
      onLoadingChange: () => {},
      onLoaded: (items) => {
        state2 = applyLoadedProfiles(state2, items);
      },
      onUnauthenticated: () => {},
      onUnavailable: () => {},
      onError: () => {},
    });
    await new Promise((r) => setTimeout(r, 5));

    live2 = { status: "unauthenticated", ownerKey: null };
    c2.syncSessionContext({ status: "unauthenticated", ownerKey: null });
    state2 = applySessionCleared(state2);

    live2 = { status: "authenticated", ownerKey: "user-B" };
    c2.syncSessionContext({ status: "authenticated", ownerKey: "user-B" });
    const bReq = c2.startLoad({
      ownerKey: "user-B",
      getAccessToken: () => "tok-B2",
      getLiveContext: () => live2,
      unavailableFallbackMessage: "Unavailable",
      fetchList: async () => secondFetch,
      onLoadingChange: () => {},
      onLoaded: (items) => {
        state2 = applyLoadedProfiles(state2, items);
      },
      onUnauthenticated: () => {},
      onUnavailable: () => {},
      onError: () => {},
    });
    await new Promise((r) => setTimeout(r, 5));

    // User B finishes FIRST:
    releaseSecond([userBProfile]);
    await bReq;
    assert.deepEqual(state2.savedProfiles.map((p) => p.id), ["prof-b-1"]);

    // User A's delayed response arrives AFTER User B already completed:
    releaseDelayedFirst([userAProfile]);
    await delayedReq;
    assert.deepEqual(state2.savedProfiles.map((p) => p.id), ["prof-b-1"]);
    assert.equal(resolveActiveProfile(state2)?.id, "prof-b-1");
    assert.equal(c2.getSnapshot().loadedOwnerKey, "user-B");
  });

  it("ignores delayed profile responses arriving after logout while preserving synthetic preview", async () => {
    const coordinator = createProfileLoadCoordinator();
    let workspaceState = activateSyntheticSamplePreview(createInitialWorkspaceState());
    let liveSession = { status: "authenticated", ownerKey: "user-A" };

    const privateProfile = {
      id: "prof-private-1",
      label: "Private Chart",
      input_calendar: "AD",
      entered_date: "1995-05-05",
      date_ad: "1995-05-05",
      bs_conversion_status: "resolved",
      time_certainty: "exact",
      time_local: "07:00",
      place_name: "Kathmandu",
      latitude: 27.7172,
      longitude: 85.324,
      timezone: "Asia/Kathmandu",
      is_synthetic_sample: false,
    };

    let releaseSlowFetch;
    const slowFetch = new Promise((res) => {
      releaseSlowFetch = res;
    });

    coordinator.syncSessionContext({ status: "authenticated", ownerKey: "user-A" });
    const reqP = coordinator.startLoad({
      ownerKey: "user-A",
      getAccessToken: () => "tok-A",
      getLiveContext: () => liveSession,
      unavailableFallbackMessage: "Unavailable",
      fetchList: async () => slowFetch,
      onLoadingChange: () => {},
      onLoaded: (items) => {
        workspaceState = applyLoadedProfiles(workspaceState, items);
      },
      onUnauthenticated: () => {},
      onUnavailable: () => {},
      onError: () => {},
    });
    await new Promise((r) => setTimeout(r, 5));

    // User logs out before response returns
    liveSession = { status: "unauthenticated", ownerKey: null };
    coordinator.syncSessionContext({ status: "unauthenticated", ownerKey: null });
    workspaceState = applySessionCleared(workspaceState);

    // Late response returns AFTER logout -> MUST NOT restore private profiles
    releaseSlowFetch([privateProfile]);
    await reqP;

    assert.equal(workspaceState.savedProfiles.length, 0);
    assert.equal(coordinator.getSnapshot().loadedOwnerKey, null);
    assert.equal(resolveVisibleProfiles(workspaceState).length, 1);
    assert.equal(resolveActiveProfile(workspaceState)?.is_synthetic_sample, true);
  });
});
