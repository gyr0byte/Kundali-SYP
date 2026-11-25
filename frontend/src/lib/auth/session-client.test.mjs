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

  it("keeps registration decoupled from automatic sign-in", async () => {
    const manager = createAuthSessionManager({
      locks: null,
      fetchImpl: async (url) => {
        assert.equal(url, "/api/auth/register");
        return new Response(JSON.stringify({ user: SAMPLE_USER }), {
          status: 201,
          headers: { "content-type": "application/json" },
        });
      },
    });

    const res = await manager.register("asha@example.com", "ValidPass123!");
    assert.equal(res.ok, true);
    assert.equal(res.status, 201);
    assert.equal(manager.getSnapshot().isAuthenticated, false);
    assert.equal(manager.getSnapshot().status, "checking");
    manager.dispose();
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
    // First test that malformed/expired/refresh-token broadcasts are ignored when logged out
    await tabA.logout();
    assert.equal(tabA.getSnapshot().status, "unauthenticated");
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    logoutChannel.postMessage({
      type: "SESSION_UPDATED",
      senderId: "evil-or-stale",
      user: SAMPLE_USER,
      accessToken: "spoofed",
      expiresAtMs: nowMs - 1000, // expired
    });
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    logoutChannel.postMessage({
      type: "SESSION_UPDATED",
      senderId: "smuggling-tab",
      user: SAMPLE_USER,
      accessToken: "ok-tok",
      expiresAtMs: nowMs + 60_000,
      refresh_token: "must-never-be-accepted",
    });
    assert.equal(tabB.getSnapshot().status, "unauthenticated");

    logoutChannel.close();
    tabA.dispose();
    tabB.dispose();
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
