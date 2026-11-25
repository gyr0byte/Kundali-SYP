import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ApiClientError, resolveApiBaseUrl } from "./client.ts";
import {
  createProfile,
  deleteProfile,
  listProfiles,
  mapBirthProfileDto,
  toCreateProfilePayload,
  updateProfile,
} from "./profiles.ts";
import { SAMPLE_NORTH_LONDON_PROFILE } from "../kundali/sample-north-london.ts";
import {
  activateSyntheticSamplePreview,
  applyCreatedProfile,
  applyDeletedProfile,
  applyLoadedProfiles,
  applySessionCleared,
  applyUpdatedProfile,
  createInitialWorkspaceState,
  getInitialProfileFormValues,
  resolveActiveProfile,
  resolveVisibleProfiles,
  validateProfileFormInput,
} from "../kundali/profile-workflow.ts";

describe("API client authentication boundary and configuration", () => {
  it("never calls fetch when access token provider is missing or returns null", async () => {
    let fetchCalls = 0;
    const spyFetch = async () => {
      fetchCalls += 1;
      throw new Error("Should never execute network request without access token");
    };

    await assert.rejects(
      () => listProfiles({ getAccessToken: () => null, fetchImpl: spyFetch }),
      (err) => err instanceof ApiClientError && err.code === "AUTH_REQUIRED" && err.status === 401
    );
    await assert.rejects(
      () =>
        createProfile(
          { getAccessToken: async () => "   ", fetchImpl: spyFetch },
          {
            label: "Asha",
            input_calendar: "AD",
            entered_date: "1998-07-31",
            time_certainty: "exact",
            time_local: "08:30",
            place_name: "Kathmandu",
            latitude: 27.7172,
            longitude: 85.324,
            timezone: "Asia/Kathmandu",
          }
        ),
      (err) => err instanceof ApiClientError && err.code === "AUTH_REQUIRED"
    );
    assert.equal(fetchCalls, 0);
  });

  it("injects Bearer token, sends credentials=omit, and respects configured baseUrl", async () => {
    const calls = [];
    const mockFetch = async (url, init) => {
      calls.push({ url, init });
      return new Response(
        JSON.stringify({ items: [], total: 0, limit: 25, offset: 0 }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    };

    const res = await listProfiles(
      {
        getAccessToken: async () => "token-abc-123",
        baseUrl: "https://api.kundali.local/api/v1/",
        fetchImpl: mockFetch,
      },
      { limit: 25, offset: 0 }
    );

    assert.equal(res.total, 0);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "https://api.kundali.local/api/v1/profiles?limit=25&offset=0");
    assert.equal(calls[0].init.method, "GET");
    assert.equal(calls[0].init.credentials, "omit");
    assert.equal(calls[0].init.headers.Authorization, "Bearer token-abc-123");
    assert.equal(resolveApiBaseUrl("http://localhost:8000/api/v1///"), "http://localhost:8000/api/v1");
  });
});

describe("Birth profile CRUD payloads, DTO mapping, and synthetic isolation", () => {
  const sampleBackendDto = {
    id: "11111111-1111-1111-1111-111111111111",
    owner_id: "22222222-2222-2222-2222-222222222222",
    label: "Family Member",
    input_calendar: "BS",
    entered_date: "2055-04-15",
    date_ad: null,
    bs_conversion_status: "awaiting_bs_conversion",
    time_certainty: "unknown",
    time_local: "08:30",
    place_name: "Pokhara, Nepal",
    latitude: 28.2096,
    longitude: 83.9856,
    timezone: "Asia/Kathmandu",
    created_at: "2026-11-25T10:00:00Z",
    updated_at: "2026-11-25T10:00:00Z",
  };

  it("maps DTO cleanly and preserves time_local=null when certainty is unknown", () => {
    const mapped = mapBirthProfileDto(sampleBackendDto);
    assert.equal(mapped.date_ad, null);
    assert.equal(mapped.bs_conversion_status, "awaiting_bs_conversion");
    assert.equal(mapped.time_local, null);
    assert.equal(mapped.is_synthetic_sample, false);
  });

  it("sends POST, PATCH, DELETE cleanly and keeps BS/unknown invariants intact", async () => {
    const requests = [];
    const mockFetch = async (url, init) => {
      requests.push({ url, method: init.method, body: init.body ? JSON.parse(init.body) : null });
      if (init.method === "POST") {
        return new Response(
          JSON.stringify({ ...sampleBackendDto, time_local: null }),
          { status: 201, headers: { "content-type": "application/json" } }
        );
      }
      if (init.method === "PATCH") {
        return new Response(
          JSON.stringify({ ...sampleBackendDto, label: "Updated Name", time_local: null }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      }
      return new Response(null, { status: 204 });
    };
    const cfg = {
      getAccessToken: () => "jwt-token",
      baseUrl: "http://localhost:8000/api/v1",
      fetchImpl: mockFetch,
    };

    const created = await createProfile(cfg, {
      label: "  Family Member  ",
      input_calendar: "BS",
      entered_date: "2055-04-15",
      time_certainty: "unknown",
      time_local: "08:30",
      place_name: " Pokhara, Nepal ",
      latitude: 28.2096,
      longitude: 83.9856,
      timezone: " Asia/Kathmandu ",
    });
    assert.equal(created.bs_conversion_status, "awaiting_bs_conversion");
    assert.equal(requests[0].method, "POST");
    assert.equal(requests[0].url, "http://localhost:8000/api/v1/profiles");
    assert.equal(requests[0].body.time_local, null);

    const updated = await updateProfile(cfg, created.id, {
      label: "Updated Name",
      time_certainty: "unknown",
    });
    assert.equal(updated.label, "Updated Name");
    assert.equal(requests[1].method, "PATCH");
    assert.equal(requests[1].body.time_local, null);

    await deleteProfile(cfg, created.id);
    assert.equal(requests[2].method, "DELETE");
    assert.equal(requests[2].url, `http://localhost:8000/api/v1/profiles/${created.id}`);
  });

  it("refuses any attempt to submit, update, or delete the synthetic North London fixture", async () => {
    let fetchCalls = 0;
    const spyFetch = async () => {
      fetchCalls += 1;
      throw new Error("Synthetic sample must never trigger network API calls");
    };
    const cfg = { getAccessToken: () => "jwt-token", fetchImpl: spyFetch };

    assert.throws(() => toCreateProfilePayload(SAMPLE_NORTH_LONDON_PROFILE), ApiClientError);
    await assert.rejects(() => createProfile(cfg, SAMPLE_NORTH_LONDON_PROFILE), ApiClientError);
    await assert.rejects(
      () => updateProfile(cfg, SAMPLE_NORTH_LONDON_PROFILE.id, { label: "Edit Sample" }),
      ApiClientError
    );
    await assert.rejects(() => deleteProfile(cfg, SAMPLE_NORTH_LONDON_PROFILE.id), ApiClientError);
    assert.equal(fetchCalls, 0);
  });

  it("classifies 401, 403, 404, 422, 503, and network errors accurately", async () => {
    const cases = [
      { status: 401, code: "UNAUTHORIZED", body: { detail: "Invalid token" } },
      { status: 403, code: "FORBIDDEN", body: { detail: "Forbidden" } },
      { status: 404, code: "NOT_FOUND", body: { detail: "Item not found" } },
      {
        status: 422,
        code: "VALIDATION_ERROR",
        body: {
          detail: [
            {
              type: "value_error",
              loc: ["body", "timezone"],
              msg: "Value error, Timezone must be a valid region-based IANA identifier or UTC",
            },
          ],
        },
      },
      { status: 503, code: "BACKEND_UNAVAILABLE", body: { detail: "Down" } },
    ];

    for (const c of cases) {
      const mockFetch = async () =>
        new Response(JSON.stringify(c.body), {
          status: c.status,
          headers: { "content-type": "application/json" },
        });
      await assert.rejects(
        () => listProfiles({ getAccessToken: () => "jwt", fetchImpl: mockFetch }),
        (err) => {
          assert(err instanceof ApiClientError);
          assert.equal(err.code, c.code);
          assert.equal(err.status, c.status);
          if (c.code === "VALIDATION_ERROR") {
            assert.deepEqual(err.validationMessages, [
              "Timezone must be a valid region-based IANA identifier or UTC",
            ]);
          }
          return true;
        }
      );
    }

    await assert.rejects(
      () =>
        listProfiles({
          getAccessToken: () => "jwt",
          fetchImpl: async () => {
            throw new TypeError("Failed to fetch");
          },
        }),
      (err) => err instanceof ApiClientError && err.code === "NETWORK_ERROR" && err.status === null
    );
  });
});

describe("Birth profile form defaults and multi-profile workflow state", () => {
  it("uses blank explicit inputs with no prefilled Kathmandu place or coordinates", () => {
    const defaults = getInitialProfileFormValues(null);
    assert.equal(defaults.label, "");
    assert.equal(defaults.enteredDate, "");
    assert.equal(defaults.timeLocal, "");
    assert.equal(defaults.placeName, "");
    assert.equal(defaults.timezone, "");
    assert.equal(defaults.latitude, "");
    assert.equal(defaults.longitude, "");

    const emptyCoordResult = validateProfileFormInput({
      ...defaults,
      label: "Test Person",
      enteredDate: "1998-07-31",
      timeLocal: "08:30",
      placeName: "Berlin, Germany",
      timezone: "Europe/Berlin",
    });
    assert.equal(emptyCoordResult.payload, null);
    assert.match(emptyCoordResult.error ?? "", /latitude and longitude/i);
  });

  it("manages create, select, edit, delete, and synthetic sample preview independently", () => {
    const profileA = {
      id: "aaaa-1",
      label: "Asha",
      input_calendar: "AD",
      entered_date: "1998-07-31",
      date_ad: "1998-07-31",
      bs_conversion_status: "resolved",
      time_certainty: "exact",
      time_local: "08:30",
      place_name: "Kathmandu",
      latitude: 27.7172,
      longitude: 85.324,
      timezone: "Asia/Kathmandu",
      is_synthetic_sample: false,
    };
    const profileB = { ...profileA, id: "bbbb-2", label: "Ramesh" };

    let state = createInitialWorkspaceState();
    state = applyLoadedProfiles(state, [profileA]);
    assert.equal(state.savedProfiles.length, 1);
    assert.equal(state.activeProfileId, "aaaa-1");

    state = applyCreatedProfile(state, profileB);
    assert.equal(state.savedProfiles.length, 2);
    assert.equal(state.activeProfileId, "bbbb-2");

    // Opening synthetic preview preserves savedProfiles untouched
    state = activateSyntheticSamplePreview(state);
    assert.equal(resolveActiveProfile(state)?.is_synthetic_sample, true);
    assert.equal(state.savedProfiles.length, 2);
    assert.equal(resolveVisibleProfiles(state).length, 3);

    // Editing a saved profile switches back cleanly without dropping other profiles
    state = applyUpdatedProfile(state, { ...profileB, label: "Ramesh Updated" });
    assert.equal(resolveActiveProfile(state)?.label, "Ramesh Updated");
    assert.equal(state.savedProfiles.length, 2);

    // Deleting active saved profile falls back to remaining saved profile
    state = applyDeletedProfile(state, "bbbb-2");
    assert.equal(state.savedProfiles.length, 1);
    assert.equal(state.activeProfileId, "aaaa-1");

    // Clearing definitive session clears saved profiles while keeping synthetic sample preview accessible
    state = activateSyntheticSamplePreview(state);
    state = applySessionCleared(state);
    assert.equal(state.savedProfiles.length, 0);
    assert.equal(state.activeProfileId, SAMPLE_NORTH_LONDON_PROFILE.id);
    assert.equal(resolveActiveProfile(state)?.is_synthetic_sample, true);
  });
});

describe("API client single 401 refresh-and-retry integration", () => {
  it("retries at most once on HTTP 401, stops on second 401, and never retries 403/422", async () => {
    const authHeaders = [];
    let refreshCalls = 0;

    const okAfterRefresh = await listProfiles({
      getAccessToken: () => "expired-tok",
      onUnauthorizedRefresh: async (failedTok) => {
        assert.equal(failedTok, "expired-tok");
        refreshCalls += 1;
        return "fresh-tok";
      },
      fetchImpl: async (_url, init) => {
        authHeaders.push(init.headers.Authorization);
        if (authHeaders.length === 1) {
          return new Response(JSON.stringify({ detail: "Expired" }), {
            status: 401,
            headers: { "content-type": "application/json" },
          });
        }
        return new Response(
          JSON.stringify({ items: [], total: 0, limit: 25, offset: 0 }),
          { status: 200, headers: { "content-type": "application/json" } }
        );
      },
    });
    assert.equal(okAfterRefresh.total, 0);
    assert.equal(refreshCalls, 1);
    assert.deepEqual(authHeaders, ["Bearer expired-tok", "Bearer fresh-tok"]);

    // Stops cleanly after second 401 without looping
    let double401RefreshCount = 0;
    let double401FetchCount = 0;
    await assert.rejects(
      () =>
        listProfiles({
          getAccessToken: () => "stale-1",
          onUnauthorizedRefresh: async () => {
            double401RefreshCount += 1;
            return "still-bad-2";
          },
          fetchImpl: async () => {
            double401FetchCount += 1;
            return new Response(JSON.stringify({ detail: "Unauthorized" }), {
              status: 401,
              headers: { "content-type": "application/json" },
            });
          },
        }),
      (err) => err instanceof ApiClientError && err.code === "UNAUTHORIZED" && err.status === 401
    );
    assert.equal(double401RefreshCount, 1);
    assert.equal(double401FetchCount, 2);

    // Never invokes refresh hook on 403 or 422
    for (const status of [403, 422]) {
      let unwantedRefresh = 0;
      await assert.rejects(
        () =>
          listProfiles({
            getAccessToken: () => "valid-tok",
            onUnauthorizedRefresh: async () => {
              unwantedRefresh += 1;
              return "should-not-happen";
            },
            fetchImpl: async () =>
              new Response(JSON.stringify({ detail: "Non-auth error" }), {
                status,
                headers: { "content-type": "application/json" },
              }),
          }),
        (err) => err instanceof ApiClientError && err.status === status
      );
      assert.equal(unwantedRefresh, 0);
    }
  });
});
