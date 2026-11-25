import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  AUTH_BROADCAST_CHANNEL,
  AUTH_WEB_LOCK_NAME,
  createAuthSessionManager,
} from "./session-client.ts";

function makeJwtWithExp(expSeconds) {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(
    JSON.stringify({ sub: "user-123", role: "user", exp: expSeconds })
  ).toString("base64url");
  return `${header}.${payload}.sig`;
}

const SAMPLE_USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "asha@example.com",
  role: "user",
  language: "ne",
  is_active: true,
  created_at: "2026-11-25T10:00:00Z",
};

function createMemoryBroadcastBus() {
  const channelsByName = new Map();

  function factory(name) {
    if (!channelsByName.has(name)) {
      channelsByName.set(name, new Set());
    }
    const peers = channelsByName.get(name);
    const listeners = new Set();
    let closed = false;

    const instance = {
      onmessage: null,
      addEventListener(type, listener) {
        if (type === "message") {
          listeners.add(listener);
        }
      },
      removeEventListener(type, listener) {
        if (type === "message") {
          listeners.delete(listener);
        }
      },
      postMessage(message) {
        if (closed) {
          throw new Error("Channel is closed");
        }
        // Snapshot clone without retaining object references
        const cloned = JSON.parse(JSON.stringify(message));
        for (const peer of peers) {
          if (peer !== instance && !peer._isClosed()) {
            peer._deliver(cloned);
          }
        }
      },
      close() {
        closed = true;
        listeners.clear();
        peers.delete(instance);
      },
      _isClosed() {
        return closed;
      },
      _deliver(data) {
        const event = { data };
        if (typeof instance.onmessage === "function") {
          instance.onmessage(event);
        }
        for (const listener of listeners) {
          listener(event);
        }
      },
    };
    peers.add(instance);
    return instance;
  }

  return { factory, channelsByName };
}

function createFakeLockManager() {
  const tails = new Map();
  const acquiredNames = [];

  return {
    acquiredNames,
    async request(name, callback) {
      acquiredNames.push(name);
      const previous = tails.get(name) ?? Promise.resolve();
      let releaseCurrent;
      const current = new Promise((resolve) => {
        releaseCurrent = resolve;
      });
      tails.set(
        name,
        previous.then(() => current)
      );
      await previous;
      try {
        return await callback();
      } finally {
        releaseCurrent();
      }
    },
  };
}

describe("In-memory session bootstrap, login recovery, and storage isolation", () => {
  it("handles missing cookie 200 { authenticated: false } as unauthenticated without storage access", async () => {
    let storageReads = 0;
    let storageWrites = 0;
    const origLocal = globalThis.localStorage;
    const origSession = globalThis.sessionStorage;
    const spyStorage = {
      getItem() {
        storageReads += 1;
        return null;
      },
      setItem() {
        storageWrites += 1;
      },
      removeItem() {
        storageWrites += 1;
      },
    };
    Object.defineProperty(globalThis, "localStorage", { value: spyStorage, configurable: true });
    Object.defineProperty(globalThis, "sessionStorage", { value: spyStorage, configurable: true });

    try {
      const calls = [];
      const manager = createAuthSessionManager({
        locks: null,
        fetchImpl: async (url, init) => {
          calls.push({ url, init });
          return new Response(JSON.stringify({ authenticated: false }), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        },
      });

      assert.equal(manager.getSnapshot().status, "checking");
      const snapshot = await manager.bootstrap();
      assert.equal(snapshot.status, "unauthenticated");
      assert.equal(snapshot.isAuthenticated, false);
      assert.equal(snapshot.user, null);
      assert.equal(await manager.getAccessToken(), null);
      assert.equal(calls.length, 1);
      assert.equal(calls[0].url, "/api/auth/refresh");
      assert.equal(calls[0].init.credentials, "same-origin");
      assert.equal(calls[0].init.headers["X-Kundali-CSRF"], "1");
      assert.equal(storageReads, 0);
      assert.equal(storageWrites, 0);
      manager.dispose();
    } finally {
      if (origLocal === undefined) {
        delete globalThis.localStorage;
      } else {
        Object.defineProperty(globalThis, "localStorage", { value: origLocal, configurable: true });
      }
      if (origSession === undefined) {
        delete globalThis.sessionStorage;
      } else {
        Object.defineProperty(globalThis, "sessionStorage", { value: origSession, configurable: true });
      }
    }
  });

  it("restores authenticated session cleanly and deduplicates concurrent Strict-Mode bootstraps", async () => {
    const nowMs = 1_700_000_000_000;
    const expSec = Math.floor((nowMs + 15 * 60 * 1000) / 1000);
    const token = makeJwtWithExp(expSec);
    let refreshCount = 0;

    const manager = createAuthSessionManager({
      locks: null,
      now: () => nowMs,
      fetchImpl: async () => {
        refreshCount += 1;
        await new Promise((r) => setTimeout(r, 10));
        return new Response(
          JSON.stringify({
            authenticated: true,
            access_token: token,
            expires_at_ms: expSec * 1000,
            user: SAMPLE_USER,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      },
    });

    const [s1, s2, tok1, tok2] = await Promise.all([
      manager.bootstrap(),
      manager.bootstrap(),
      manager.getAccessToken(),
      manager.getAccessToken(),
    ]);

    assert.equal(refreshCount, 1);
    assert.equal(s1.status, "authenticated");
    assert.equal(s2.status, "authenticated");
    assert.equal(s1.user?.email, SAMPLE_USER.email);
    assert.equal(tok1, token);
    assert.equal(tok2, token);
    manager.dispose();
  });

  it("handles temporary 503 during bootstrap/rotation without clearing cookie and recovers on retrySession", async () => {
    const nowMs = 1_700_000_000_000;
    const expSec = Math.floor((nowMs + 10 * 60 * 1000) / 1000);
    const token = makeJwtWithExp(expSec);
    let attempt = 0;

    const manager = createAuthSessionManager({
      locks: null,
      now: () => nowMs,
      fetchImpl: async () => {
        attempt += 1;
        if (attempt === 1) {
          return new Response(
            JSON.stringify({
              code: "BACKEND_UNAVAILABLE",
              message: "Session cookie rotated, temporary /me error",
              rotated: true,
            }),
            { status: 503, headers: { "content-type": "application/json" } }
          );
        }
        return new Response(
          JSON.stringify({
            authenticated: true,
            access_token: token,
            expires_at_ms: expSec * 1000,
            user: SAMPLE_USER,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      },
    });

    const failedSnap = await manager.bootstrap();
    assert.equal(failedSnap.status, "unavailable");
    assert.equal(failedSnap.hasRecoverableSession, true);
    assert.equal(failedSnap.error?.retryable, true);

    const recoveredSnap = await manager.retrySession();
    assert.equal(recoveredSnap.status, "authenticated");
    assert.equal(await manager.getAccessToken(), token);
    manager.dispose();
  });

  it("recovers once after login returns 503 with session_established=true without lying about credentials", async () => {
    const nowMs = 1_700_000_000_000;
    const expSec = Math.floor((nowMs + 15 * 60 * 1000) / 1000);
    const recoveredToken = makeJwtWithExp(expSec);
    const calls = [];

    const manager = createAuthSessionManager({
      locks: null,
      now: () => nowMs,
      fetchImpl: async (url) => {
        calls.push(url);
        if (url === "/api/auth/login") {
          return new Response(
            JSON.stringify({
              code: "BACKEND_UNAVAILABLE",
              message: "Signed in, /me timed out",
              session_established: true,
            }),
            { status: 503, headers: { "content-type": "application/json" } }
          );
        }
        return new Response(
          JSON.stringify({
            authenticated: true,
            access_token: recoveredToken,
            expires_at_ms: expSec * 1000,
            user: SAMPLE_USER,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      },
    });

    const result = await manager.login("asha@example.com", "ValidPass123!");
    assert.equal(result.ok, true);
    assert.equal(result.sessionEstablished, true);
    assert.equal(manager.getSnapshot().status, "authenticated");
    assert.equal(await manager.getAccessToken(), recoveredToken);
    assert.deepEqual(calls, ["/api/auth/login", "/api/auth/refresh"]);

    // Second scenario: login session_established=true followed by 503 on recovery refresh stays recoverable
    const unavailableManager = createAuthSessionManager({
      locks: null,
      now: () => nowMs,
      fetchImpl: async (url) => {
        if (url === "/api/auth/login") {
          return new Response(
            JSON.stringify({
              code: "BACKEND_UNAVAILABLE",
              message: "Cookie saved, /me unavailable",
              session_established: true,
            }),
            { status: 503, headers: { "content-type": "application/json" } }
          );
        }
        return new Response(JSON.stringify({ code: "BACKEND_UNAVAILABLE", message: "Still down" }), {
          status: 503,
          headers: { "content-type": "application/json" },
        });
      },
    });
    const recoveryFail = await unavailableManager.login("asha@example.com", "ValidPass123!");
    assert.equal(recoveryFail.ok, false);
    assert.equal(recoveryFail.code, "SESSION_RECOVERY_UNAVAILABLE");
    assert.equal(recoveryFail.sessionEstablished, true);
    assert.equal(unavailableManager.getSnapshot().status, "unavailable");
    assert.equal(unavailableManager.getSnapshot().hasRecoverableSession, true);

    manager.dispose();
    unavailableManager.dispose();
  });

  it("keeps registration decoupled from automatic sign-in and maps root UserResponse DTO", async () => {
    const requestedUrls = [];
    const manager = createAuthSessionManager({
      locks: null,
      fetchImpl: async (url) => {
        requestedUrls.push(url);
        assert.equal(url, "/api/auth/register");
        // Exact BFF 201 root-level UserResponse contract
        return new Response(JSON.stringify(SAMPLE_USER), {
          status: 201,
          headers: { "content-type": "application/json" },
        });
      },
    });

    const res = await manager.register("asha@example.com", "ValidPass123!");
    assert.equal(res.ok, true);
    assert.equal(res.status, 201);
    assert.deepEqual(res.user, SAMPLE_USER);
    assert.equal(manager.getSnapshot().isAuthenticated, false);
    assert.equal(manager.getSnapshot().status, "checking");
    assert.deepEqual(requestedUrls, ["/api/auth/register"]);

    // Rejects malformed 201 payloads that omit required UserResponse fields
    const badManager = createAuthSessionManager({
      locks: null,
      fetchImpl: async () =>
        new Response(JSON.stringify({ id: "only-id" }), {
          status: 201,
          headers: { "content-type": "application/json" },
        }),
    });
    const badRes = await badManager.register("asha@example.com", "ValidPass123!");
    assert.equal(badRes.ok, false);
    assert.equal(badRes.code, "INVALID_BACKEND_RESPONSE");

    manager.dispose();
    badManager.dispose();
  });
});

describe("Single-flight proactive/401 refresh and cross-tab coordination", () => {
  it("coalesces concurrent refreshOnUnauthorized calls and avoids re-rotating when token already rotated", async () => {
    let nowMs = 1_700_000_000_000;
    const oldToken = makeJwtWithExp(Math.floor((nowMs + 30_000) / 1000));
    const rotatedToken = makeJwtWithExp(Math.floor((nowMs + 900_000) / 1000));
    let refreshHits = 0;

    const manager = createAuthSessionManager({
      locks: null,
      now: () => nowMs,
      fetchImpl: async (url) => {
        if (url === "/api/auth/login") {
          return new Response(
            JSON.stringify({
              authenticated: true,
              access_token: oldToken,
              expires_at_ms: nowMs + 30_000,
              user: SAMPLE_USER,
            }),
            { status: 200, headers: { "content-type": "application/json" } }
          );
        }
        refreshHits += 1;
        await new Promise((r) => setTimeout(r, 10));
        return new Response(
          JSON.stringify({
            authenticated: true,
            access_token: rotatedToken,
            expires_at_ms: nowMs + 900_000,
            user: SAMPLE_USER,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      },
    });

    await manager.login("asha@example.com", "ValidPass123!");
    const [r1, r2] = await Promise.all([
      manager.refreshOnUnauthorized(oldToken),
      manager.refreshOnUnauthorized(oldToken),
    ]);
    assert.equal(r1, rotatedToken);
    assert.equal(r2, rotatedToken);
    assert.equal(refreshHits, 1);

    // Late 401 still carrying oldToken returns rotatedToken immediately without a second rotation
    const r3 = await manager.refreshOnUnauthorized(oldToken);
    assert.equal(r3, rotatedToken);
    assert.equal(refreshHits, 1);

    // Proactive refresh when within leeway preserves still-unexpired token on temporary 503
    nowMs += 850_000; // 50s remaining (< 60s default leeway)
    const manager2 = createAuthSessionManager({
      locks: null,
      now: () => nowMs,
      fetchImpl: async (url) => {
        if (url === "/api/auth/login") {
          return new Response(
            JSON.stringify({
              authenticated: true,
              access_token: rotatedToken,
              expires_at_ms: nowMs + 45_000,
              user: SAMPLE_USER,
            }),
            { status: 200, headers: { "content-type": "application/json" } }
          );
        }
        return new Response(JSON.stringify({ code: "BACKEND_UNAVAILABLE" }), {
          status: 503,
          headers: { "content-type": "application/json" },
        });
      },
    });
    await manager2.login("asha@example.com", "ValidPass123!");
    assert.equal(await manager2.getAccessToken(), rotatedToken);
    assert.equal(manager2.getSnapshot().status, "authenticated");

    manager.dispose();
    manager2.dispose();
  });

  it("coordinates cross-tab refresh with Web Locks + BroadcastChannel and rejects invalid/refresh-token broadcasts", async () => {
    const nowMs = 1_700_000_000_000;
    const freshToken = makeJwtWithExp(Math.floor((nowMs + 600_000) / 1000));
    const bus = createMemoryBroadcastBus();
    const lockManager = createFakeLockManager();
    const outgoingMessages = [];
    let backendRefreshCalls = 0;

    const createObservedChannel = (name) => {
      const ch = bus.factory(name);
      const origPost = ch.postMessage.bind(ch);
      ch.postMessage = (msg) => {
        outgoingMessages.push(msg);
        origPost(msg);
      };
      return ch;
    };

    const sharedFetch = async () => {
      backendRefreshCalls += 1;
      await new Promise((r) => setTimeout(r, 15));
      return new Response(
        JSON.stringify({
          authenticated: true,
          access_token: freshToken,
          expires_at_ms: nowMs + 600_000,
          user: SAMPLE_USER,
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    };

    const tabA = createAuthSessionManager({
      now: () => nowMs,
      locks: lockManager,
      broadcastChannelFactory: createObservedChannel,
      fetchImpl: sharedFetch,
    });
    const tabB = createAuthSessionManager({
      now: () => nowMs,
      locks: lockManager,
      broadcastChannelFactory: createObservedChannel,
      fetchImpl: sharedFetch,
    });

    const [snapA, snapB] = await Promise.all([tabA.bootstrap(), tabB.bootstrap()]);
    assert.equal(backendRefreshCalls, 1);
    assert.equal(snapA.status, "authenticated");
    assert.equal(snapB.status, "authenticated");
    assert.equal(await tabB.getAccessToken(), freshToken);
    assert.ok(lockManager.acquiredNames.every((n) => n === AUTH_WEB_LOCK_NAME));
    assert.equal(outgoingMessages.length, 1);
    assert.equal("refresh_token" in outgoingMessages[0], false);
    assert.equal("refreshToken" in outgoingMessages[0], false);

    // Logout in Tab A propagates LOGOUT to Tab B immediately
    const logoutChannel = bus.factory(AUTH_BROADCAST_CHANNEL);
    await tabA.logout();
    assert.equal(tabA.getSnapshot().status, "unauthenticated");
    assert.equal(tabB.getSnapshot().status, "unauthenticated");
    // Rejects invalid broadcast shapes, bad JWTs, missing/past/inflated expiry, missing user metadata, or nested refresh tokens
    logoutChannel.postMessage({
      type: "SESSION_UPDATED",
      senderId: "evil-or-stale",
      user: SAMPLE_USER,
      accessToken: freshToken,
      expiresAtMs: nowMs - 1000, // expired
    });
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    logoutChannel.postMessage({
      type: "SESSION_UPDATED",
      senderId: "null-expiry",
      user: SAMPLE_USER,
      accessToken: freshToken,
      expiresAtMs: null,
    });
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    logoutChannel.postMessage({
      type: "SESSION_UPDATED",
      senderId: "nan-expiry",
      user: SAMPLE_USER,
      accessToken: freshToken,
      expiresAtMs: Number.NaN,
    });
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    logoutChannel.postMessage({
      type: "SESSION_UPDATED",
      senderId: "bad-jwt-shape",
      user: SAMPLE_USER,
      accessToken: "not-three-segments",
      expiresAtMs: nowMs + 60_000,
    });
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    const noExpJwt = `${Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url")}.${Buffer.from(JSON.stringify({ sub: "user-123" })).toString("base64url")}.sig`;
    logoutChannel.postMessage({
      type: "SESSION_UPDATED",
      senderId: "missing-jwt-exp",
      user: SAMPLE_USER,
      accessToken: noExpJwt,
      expiresAtMs: nowMs + 60_000,
    });
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    logoutChannel.postMessage({
      type: "SESSION_UPDATED",
      senderId: "inflated-expiry",
      user: SAMPLE_USER,
      accessToken: freshToken,
      expiresAtMs: nowMs + 60_000_000,
    });
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    logoutChannel.postMessage({
      type: "SESSION_UPDATED",
      senderId: "incomplete-user",
      user: { id: "u1", email: "a@example.com" },
      accessToken: freshToken,
      expiresAtMs: nowMs + 600_000,
    });
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    logoutChannel.postMessage({
      type: "SESSION_UPDATED",
      senderId: "smuggling-tab",
      user: SAMPLE_USER,
      accessToken: freshToken,
      expiresAtMs: nowMs + 60_000,
      nested: { refreshToken: "must-never-be-accepted" },
    });
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    // Valid broadcast with valid JWT + future exp + complete user IS accepted cleanly
    const validBroadcaster = bus.factory(AUTH_BROADCAST_CHANNEL);
    validBroadcaster.postMessage({
      type: "SESSION_UPDATED",
      senderId: "other-valid-tab",
      user: SAMPLE_USER,
      accessToken: freshToken,
      expiresAtMs: nowMs + 600_000,
    });
    assert.equal(tabB.getSnapshot().status, "authenticated");
    assert.equal(await tabB.getAccessToken(), freshToken);
    validBroadcaster.close();

    logoutChannel.close();
    tabA.dispose();
    tabB.dispose();
  });

  it("preserves Retry-After headers on 429 rate-limited login and register responses without inventing delays when absent", async () => {
    const nowMs = 1_700_000_000_000;
    const manager = createAuthSessionManager({
      locks: null,
      now: () => nowMs,
      fetchImpl: async (url) => {
        if (url === "/api/auth/login") {
          return new Response(
            JSON.stringify({
              code: "RATE_LIMITED",
              message: "Too many attempts",
            }),
            {
              status: 429,
              headers: {
                "content-type": "application/json",
                "retry-after": "45",
              },
            }
          );
        }
        return new Response(
          JSON.stringify({
            code: "RATE_LIMITED",
            message: "Slow down",
          }),
          {
            status: 429,
            headers: { "content-type": "application/json" },
          }
        );
      },
    });

    const loginLimited = await manager.login("asha@example.com", "WrongPass123!");
    assert.equal(loginLimited.ok, false);
    assert.equal(loginLimited.status, 429);
    assert.equal(loginLimited.retryAfter, "45");
    assert.equal(loginLimited.retryAfterSeconds, 45);

    const registerLimitedNoHeader = await manager.register("asha@example.com", "ValidPass123!");
    assert.equal(registerLimitedNoHeader.ok, false);
    assert.equal(registerLimitedNoHeader.status, 429);
    assert.equal(registerLimitedNoHeader.retryAfter, null);
    assert.equal(registerLimitedNoHeader.retryAfterSeconds, null);

    manager.dispose();
  });
});

describe("logout and logoutAll truthfulness", () => {
  it("reports logout outcome honestly even if backend revocation is unconfirmed", async () => {
    const nowMs = 1_700_000_000_000;
    const token = makeJwtWithExp(Math.floor((nowMs + 600_000) / 1000));
    const manager = createAuthSessionManager({
      locks: null,
      now: () => nowMs,
      fetchImpl: async (url) => {
        if (url === "/api/auth/login") {
          return new Response(
            JSON.stringify({
              authenticated: true,
              access_token: token,
              expires_at_ms: nowMs + 600_000,
              user: SAMPLE_USER,
            }),
            { status: 200, headers: { "content-type": "application/json" } }
          );
        }
        return new Response(
          JSON.stringify({
            local_cookie_cleared: true,
            backend_logout_request_completed: false,
            backend_revocation_state: "backend_unconfirmed",
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      },
    });

    await manager.login("asha@example.com", "ValidPass123!");
    const logoutRes = await manager.logout();
    assert.equal(manager.getSnapshot().status, "unauthenticated");
    assert.equal(await manager.getAccessToken(), null);
    assert.deepEqual(logoutRes, {
      localCookieCleared: true,
      backendLogoutRequestCompleted: false,
      backendRevocationState: "backend_unconfirmed",
    });
    manager.dispose();
  });

  it("logoutAll retries at most once after 401 and preserves session if backend returns 503", async () => {
    const nowMs = 1_700_000_000_000;
    const tok1 = makeJwtWithExp(Math.floor((nowMs + 600_000) / 1000));
    const tok2 = makeJwtWithExp(Math.floor((nowMs + 900_000) / 1000));
    const bus = createMemoryBroadcastBus();
    let logoutAllAttempt = 0;

    const manager = createAuthSessionManager({
      locks: null,
      now: () => nowMs,
      broadcastChannelFactory: bus.factory,
      fetchImpl: async (url, init) => {
        if (url === "/api/auth/login") {
          return new Response(
            JSON.stringify({
              authenticated: true,
              access_token: tok1,
              expires_at_ms: nowMs + 600_000,
              user: SAMPLE_USER,
            }),
            { status: 200, headers: { "content-type": "application/json" } }
          );
        }
        if (url === "/api/auth/refresh") {
          return new Response(
            JSON.stringify({
              authenticated: true,
              access_token: tok2,
              expires_at_ms: nowMs + 900_000,
              user: SAMPLE_USER,
            }),
            { status: 200, headers: { "content-type": "application/json" } }
          );
        }
        logoutAllAttempt += 1;
        if (logoutAllAttempt === 1) {
          assert.equal(init.headers.Authorization, `Bearer ${tok1}`);
          return new Response(
            JSON.stringify({
              code: "UNAUTHORIZED",
              local_cookie_cleared: false,
              backend_logout_request_completed: false,
              backend_revocation_state: "backend_rejected",
            }),
            { status: 401, headers: { "content-type": "application/json" } }
          );
        }
        if (logoutAllAttempt === 2) {
          // Simulate temporary 503 on logout-all -> session must stay preserved locally
          assert.equal(init.headers.Authorization, `Bearer ${tok2}`);
          return new Response(
            JSON.stringify({
              code: "BACKEND_UNAVAILABLE",
              local_cookie_cleared: false,
              backend_logout_request_completed: false,
              backend_revocation_state: "backend_unconfirmed",
            }),
            { status: 503, headers: { "content-type": "application/json" } }
          );
        }
        assert.equal(init.headers.Authorization, `Bearer ${tok2}`);
        return new Response(
          JSON.stringify({
            local_cookie_cleared: true,
            backend_logout_request_completed: true,
            backend_revocation_state: "all_refresh_tokens_revoked",
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      },
    });

    const peerTab = createAuthSessionManager({
      locks: null,
      now: () => nowMs,
      broadcastChannelFactory: bus.factory,
      fetchImpl: async () => new Response(JSON.stringify({ authenticated: false }), { status: 200 }),
    });

    await manager.login("asha@example.com", "ValidPass123!");
    assert.equal(peerTab.getSnapshot().status, "authenticated");

    // First logoutAll: 401 -> single refresh (tok2) -> retry hits 503 -> MUST NOT clear session!
    const failedAll = await manager.logoutAll();
    assert.equal(failedAll.ok, false);
    assert.equal(failedAll.backendRevocationState, "backend_unconfirmed");
    assert.equal(manager.getSnapshot().status, "authenticated");
    assert.equal(peerTab.getSnapshot().status, "authenticated");

    // Second logoutAll: succeeds -> clears local memory + broadcasts LOGOUT to peerTab
    const okAll = await manager.logoutAll();
    assert.equal(okAll.ok, true);
    assert.equal(okAll.localCookieCleared, true);
    assert.equal(okAll.backendLogoutRequestCompleted, true);
    assert.equal(okAll.backendRevocationState, "all_refresh_tokens_revoked");
    assert.equal(manager.getSnapshot().status, "unauthenticated");
    assert.equal(peerTab.getSnapshot().status, "unauthenticated");

    manager.dispose();
    peerTab.dispose();
  });
});

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("Logout vs refresh lock serialization and race protection", () => {
  it("serializes logout after an in-flight cross-tab refresh so rotated cookie R2 is revoked cleanly and delayed SESSION_UPDATED cannot reauthenticate", async () => {
    const nowMs = 1_700_000_000_000;
    const t1 = makeJwtWithExp(Math.floor((nowMs + 600_000) / 1000));
    const t2 = makeJwtWithExp(Math.floor((nowMs + 900_000) / 1000));
    const bus = createMemoryBroadcastBus();
    const lockManager = createFakeLockManager();

    let cookieJarRefresh = "R1";
    const activeRefreshTokens = new Set(["R1"]);
    const timeline = [];
    const refreshDeferred = createDeferred();

    const sharedFetch = async (url) => {
      if (url === "/api/auth/login") {
        cookieJarRefresh = "R1";
        activeRefreshTokens.add("R1");
        return new Response(
          JSON.stringify({
            authenticated: true,
            access_token: t1,
            expires_at_ms: nowMs + 600_000,
            user: SAMPLE_USER,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      if (url === "/api/auth/refresh") {
        const usedCookie = cookieJarRefresh;
        timeline.push(`refresh:start:${usedCookie}`);
        await refreshDeferred.promise;
        if (!usedCookie || !activeRefreshTokens.has(usedCookie)) {
          timeline.push("refresh:unauth");
          return new Response(JSON.stringify({ authenticated: false }), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        }
        activeRefreshTokens.delete(usedCookie);
        cookieJarRefresh = "R2";
        activeRefreshTokens.add("R2");
        timeline.push("refresh:end:R2");
        return new Response(
          JSON.stringify({
            authenticated: true,
            access_token: t2,
            expires_at_ms: nowMs + 900_000,
            user: SAMPLE_USER,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      if (url === "/api/auth/logout") {
        const revoked = cookieJarRefresh;
        timeline.push(`logout:start:${revoked}`);
        if (revoked) {
          activeRefreshTokens.delete(revoked);
        }
        cookieJarRefresh = null;
        timeline.push(`logout:end:${revoked}`);
        return new Response(
          JSON.stringify({
            local_cookie_cleared: true,
            backend_logout_request_completed: true,
            backend_revocation_state: "logout_request_accepted",
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      throw new Error(`Unexpected URL ${url}`);
    };

    const tabA = createAuthSessionManager({
      now: () => nowMs,
      locks: lockManager,
      broadcastChannelFactory: bus.factory,
      fetchImpl: sharedFetch,
    });
    const tabB = createAuthSessionManager({
      now: () => nowMs,
      locks: lockManager,
      broadcastChannelFactory: bus.factory,
      fetchImpl: sharedFetch,
    });

    await tabB.login("asha@example.com", "ValidPass123!");
    assert.equal(tabA.getSnapshot().status, "authenticated");

    // 1. Tab B begins forced refresh (R1 -> R2), stalled on refreshDeferred inside lock.
    const refreshP = tabB.refreshSession({ force: true });
    await new Promise((r) => setTimeout(r, 5));
    assert.deepEqual(timeline, ["refresh:start:R1"]);

    // 2. Tab A starts logout while Tab B's refresh is still holding the lock.
    const logoutP = tabA.logout();
    await new Promise((r) => setTimeout(r, 5));
    // Logout MUST wait for the in-flight refresh lock before sending /api/auth/logout!
    assert.deepEqual(timeline, ["refresh:start:R1"]);

    // 3. Refresh settles -> rotates R1->R2 -> releases lock -> Logout enters lock and revokes R2!
    refreshDeferred.resolve();
    const [, logoutResult] = await Promise.all([refreshP, logoutP]);

    assert.equal(logoutResult.localCookieCleared, true);
    assert.equal(logoutResult.backendRevocationState, "logout_request_accepted");
    assert.deepEqual(timeline, [
      "refresh:start:R1",
      "refresh:end:R2",
      "logout:start:R2",
      "logout:end:R2",
    ]);
    assert.equal(cookieJarRefresh, null);
    assert.equal(activeRefreshTokens.size, 0);
    assert.equal(tabA.getSnapshot().status, "unauthenticated");
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    // 4. Subsequent delayed refresh in peer tab cannot restore cookie after completed logout.
    const postLogoutTok = await tabB.refreshSession({ force: true });
    assert.equal(postLogoutTok, null);
    assert.equal(cookieJarRefresh, null);
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    tabA.dispose();
    tabB.dispose();
  });

  it("prevents delayed in-tab refresh from restoring state or cookie when logout waits cleanly (both with locks and locks=null fallback)", async () => {
    for (const useLocks of [true, false]) {
      const nowMs = 1_700_000_000_000;
      const t1 = makeJwtWithExp(Math.floor((nowMs + 600_000) / 1000));
      const t2 = makeJwtWithExp(Math.floor((nowMs + 900_000) / 1000));
      const lockManager = useLocks ? createFakeLockManager() : null;
      const refreshGate = createDeferred();
      const logoutGate = createDeferred();
      let cookieState = "R1";
      let overlapCount = 0;
      let activeOps = 0;
      const events = [];

      const manager = createAuthSessionManager({
        now: () => nowMs,
        locks: lockManager,
        fetchImpl: async (url) => {
          activeOps += 1;
          if (activeOps > 1) {
            overlapCount += 1;
          }
          try {
            if (url === "/api/auth/login") {
              cookieState = "R1";
              return new Response(
                JSON.stringify({
                  authenticated: true,
                  access_token: t1,
                  expires_at_ms: nowMs + 600_000,
                  user: SAMPLE_USER,
                }),
                { status: 200, headers: { "content-type": "application/json" } }
              );
            }
            if (url === "/api/auth/refresh") {
              events.push("refresh:enter");
              await refreshGate.promise;
              if (!cookieState) {
                events.push("refresh:no_cookie");
                return new Response(JSON.stringify({ authenticated: false }), { status: 200 });
              }
              cookieState = "R2";
              events.push("refresh:exit");
              return new Response(
                JSON.stringify({
                  authenticated: true,
                  access_token: t2,
                  expires_at_ms: nowMs + 900_000,
                  user: SAMPLE_USER,
                }),
                { status: 200, headers: { "content-type": "application/json" } }
              );
            }
            if (url === "/api/auth/logout") {
              events.push("logout:enter");
              await logoutGate.promise;
              cookieState = null;
              events.push("logout:exit");
              return new Response(
                JSON.stringify({
                  local_cookie_cleared: true,
                  backend_logout_request_completed: true,
                  backend_revocation_state: "logout_request_accepted",
                }),
                { status: 200, headers: { "content-type": "application/json" } }
              );
            }
            throw new Error(`Unexpected ${url}`);
          } finally {
            activeOps -= 1;
          }
        },
      });

      await manager.login("asha@example.com", "ValidPass123!");

      // Refresh enters first and blocks on refreshGate; logout queues strictly behind it!
      const refreshP = manager.refreshSession({ force: true });
      await new Promise((r) => setTimeout(r, 5));
      const logoutP = manager.logout();
      await new Promise((r) => setTimeout(r, 5));

      assert.deepEqual(events, ["refresh:enter"]);
      assert.equal(cookieState, "R1");

      refreshGate.resolve();
      await new Promise((r) => setTimeout(r, 5));
      // Refresh finished WITHOUT leaving authenticated state because logout was pending;
      // now logout has entered the serialized mutex/lock and awaits logoutGate.
      assert.deepEqual(events, ["refresh:enter", "refresh:exit", "logout:enter"]);

      logoutGate.resolve();
      const [refreshTok, logoutRes] = await Promise.all([refreshP, logoutP]);
      assert.equal(refreshTok, null);
      assert.equal(logoutRes.localCookieCleared, true);
      assert.equal(cookieState, null);
      assert.equal(manager.getSnapshot().status, "unauthenticated");
      assert.equal(await manager.getAccessToken(), null);
      assert.equal(overlapCount, 0);
      assert.deepEqual(events, ["refresh:enter", "refresh:exit", "logout:enter", "logout:exit"]);
      manager.dispose();
    }
  });

  it("serializes logoutAll against concurrent refresh, releases lock for a single 401 refresh retry, and preserves session on failure", async () => {
    const nowMs = 1_700_000_000_000;
    const t1 = makeJwtWithExp(Math.floor((nowMs + 600_000) / 1000));
    const t2 = makeJwtWithExp(Math.floor((nowMs + 900_000) / 1000));
    const t3 = makeJwtWithExp(Math.floor((nowMs + 1_200_000) / 1000));
    const lockManager = createFakeLockManager();
    const bus = createMemoryBroadcastBus();

    const refreshStarted = createDeferred();
    const releaseConcurrentRefresh = createDeferred();
    let refreshCallNum = 0;
    let logoutAllCallNum = 0;
    const timeline = [];

    const sharedFetch = async (url, init) => {
      if (url === "/api/auth/login") {
        return new Response(
          JSON.stringify({
            authenticated: true,
            access_token: t1,
            expires_at_ms: nowMs + 600_000,
            user: SAMPLE_USER,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      if (url === "/api/auth/refresh") {
        refreshCallNum += 1;
        const n = refreshCallNum;
        timeline.push(`refresh#${n}:start`);
        if (n === 1) {
          refreshStarted.resolve();
          await releaseConcurrentRefresh.promise;
        }
        const nextTok = n === 1 ? t2 : t3;
        const nextExpMs = n === 1 ? nowMs + 900_000 : nowMs + 1_200_000;
        timeline.push(`refresh#${n}:end`);
        return new Response(
          JSON.stringify({
            authenticated: true,
            access_token: nextTok,
            expires_at_ms: nextExpMs,
            user: SAMPLE_USER,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      if (url === "/api/auth/logout-all") {
        logoutAllCallNum += 1;
        const n = logoutAllCallNum;
        timeline.push(`logoutAll#${n}:start:${init.headers.Authorization}`);
        if (n === 1) {
          timeline.push("logoutAll#1:401");
          return new Response(
            JSON.stringify({
              code: "UNAUTHORIZED",
              local_cookie_cleared: false,
              backend_logout_request_completed: false,
              backend_revocation_state: "backend_rejected",
            }),
            { status: 401, headers: { "content-type": "application/json" } }
          );
        }
        timeline.push("logoutAll#2:200");
        return new Response(
          JSON.stringify({
            local_cookie_cleared: true,
            backend_logout_request_completed: true,
            backend_revocation_state: "all_refresh_tokens_revoked",
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      throw new Error(`Unexpected ${url}`);
    };

    const tabA = createAuthSessionManager({
      now: () => nowMs,
      locks: lockManager,
      broadcastChannelFactory: bus.factory,
      fetchImpl: sharedFetch,
    });
    const tabB = createAuthSessionManager({
      now: () => nowMs,
      locks: lockManager,
      broadcastChannelFactory: bus.factory,
      fetchImpl: sharedFetch,
    });

    await tabA.login("asha@example.com", "ValidPass123!");

    // Concurrent refresh in Tab B acquires lock first; Tab A calls logoutAll concurrently.
    const refreshP = tabB.refreshSession({ force: true });
    await refreshStarted.promise;
    const logoutAllP = tabA.logoutAll();
    await new Promise((r) => setTimeout(r, 5));

    // logoutAll must not enter until Tab B's refresh releases the shared lock.
    assert.deepEqual(timeline, ["refresh#1:start"]);

    releaseConcurrentRefresh.resolve();
    const [rTok, allRes] = await Promise.all([refreshP, logoutAllP]);
    assert.equal(rTok, t2);
    assert.equal(allRes.ok, true);
    assert.equal(allRes.backendRevocationState, "all_refresh_tokens_revoked");
    // Exact serialized timeline: refresh#1 -> logoutAll#1(t2)->401 -> refresh#2(t3) -> logoutAll#2(t3)->200
    assert.deepEqual(timeline, [
      "refresh#1:start",
      "refresh#1:end",
      `logoutAll#1:start:Bearer ${t2}`,
      "logoutAll#1:401",
      "refresh#2:start",
      "refresh#2:end",
      `logoutAll#2:start:Bearer ${t3}`,
      "logoutAll#2:200",
    ]);
    assert.equal(tabA.getSnapshot().status, "unauthenticated");
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    // Verify logoutAll stops after a single 401 retry (never loops infinitely on persistent 401)
    let endlessAttempts = 0;
    const finiteManager = createAuthSessionManager({
      now: () => nowMs,
      locks: null,
      fetchImpl: async (url) => {
        if (url === "/api/auth/login") {
          return new Response(
            JSON.stringify({
              authenticated: true,
              access_token: t1,
              expires_at_ms: nowMs + 600_000,
              user: SAMPLE_USER,
            }),
            { status: 200, headers: { "content-type": "application/json" } }
          );
        }
        if (url === "/api/auth/refresh") {
          return new Response(
            JSON.stringify({
              authenticated: true,
              access_token: t2,
              expires_at_ms: nowMs + 900_000,
              user: SAMPLE_USER,
            }),
            { status: 200, headers: { "content-type": "application/json" } }
          );
        }
        endlessAttempts += 1;
        return new Response(
          JSON.stringify({
            code: "UNAUTHORIZED",
            local_cookie_cleared: false,
            backend_logout_request_completed: false,
            backend_revocation_state: "backend_rejected",
          }),
          { status: 401, headers: { "content-type": "application/json" } }
        );
      },
    });
    await finiteManager.login("asha@example.com", "ValidPass123!");
    const persistent401 = await finiteManager.logoutAll();
    assert.equal(persistent401.ok, false);
    assert.equal(endlessAttempts, 2);
    assert.equal(finiteManager.getSnapshot().status, "authenticated");

    tabA.dispose();
    tabB.dispose();
    finiteManager.dispose();
  });

  it("ensures a delayed refresh queued behind active logout cannot restore cookie or re-authenticate peers", async () => {
    const nowMs = 1_700_000_000_000;
    const t1 = makeJwtWithExp(Math.floor((nowMs + 600_000) / 1000));
    const t2 = makeJwtWithExp(Math.floor((nowMs + 900_000) / 1000));
    const bus = createMemoryBroadcastBus();
    const lockManager = createFakeLockManager();
    const logoutStarted = createDeferred();
    const releaseLogout = createDeferred();

    let cookieJarRefresh = "R1";
    let refreshRequestsAfterLogout = 0;

    const sharedFetch = async (url) => {
      if (url === "/api/auth/login") {
        cookieJarRefresh = "R1";
        return new Response(
          JSON.stringify({
            authenticated: true,
            access_token: t1,
            expires_at_ms: nowMs + 600_000,
            user: SAMPLE_USER,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      if (url === "/api/auth/logout") {
        logoutStarted.resolve();
        await releaseLogout.promise;
        cookieJarRefresh = null;
        return new Response(
          JSON.stringify({
            local_cookie_cleared: true,
            backend_logout_request_completed: true,
            backend_revocation_state: "logout_request_accepted",
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      if (url === "/api/auth/refresh") {
        refreshRequestsAfterLogout += 1;
        if (!cookieJarRefresh) {
          return new Response(JSON.stringify({ authenticated: false }), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        }
        cookieJarRefresh = "R2";
        return new Response(
          JSON.stringify({
            authenticated: true,
            access_token: t2,
            expires_at_ms: nowMs + 900_000,
            user: SAMPLE_USER,
          }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      throw new Error(`Unexpected ${url}`);
    };

    const tabA = createAuthSessionManager({
      now: () => nowMs,
      locks: lockManager,
      broadcastChannelFactory: bus.factory,
      fetchImpl: sharedFetch,
    });
    const tabB = createAuthSessionManager({
      now: () => nowMs,
      locks: lockManager,
      broadcastChannelFactory: bus.factory,
      fetchImpl: sharedFetch,
    });

    await tabA.login("asha@example.com", "ValidPass123!");
    assert.equal(tabB.getSnapshot().status, "authenticated");

    // 1. Tab A begins logout (holds lock while /api/auth/logout is in flight)
    const logoutP = tabA.logout();
    await logoutStarted.promise;

    // 2. Tab B tries a delayed/concurrent forced refresh while Tab A holds lock
    const delayedRefreshP = tabB.refreshSession({ force: true });
    await new Promise((r) => setTimeout(r, 5));
    assert.equal(refreshRequestsAfterLogout, 0);

    // 3. Logout finishes -> clears cookie -> broadcasts final LOGOUT -> releases lock
    releaseLogout.resolve();
    const [logoutRes, delayedTok] = await Promise.all([logoutP, delayedRefreshP]);

    assert.equal(logoutRes.localCookieCleared, true);
    assert.equal(delayedTok, null);
    assert.equal(cookieJarRefresh, null);
    assert.equal(tabA.getSnapshot().status, "unauthenticated");
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    tabA.dispose();
    tabB.dispose();
  });
});
