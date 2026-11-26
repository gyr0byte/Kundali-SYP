import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { calculateChart, getChartIssue, matchesChartProfile } from "./charts.ts";
import { getProvenanceStatus } from "../kundali/chart-helpers.ts";
import { SAMPLE_NORTH_LONDON_PROFILE } from "../kundali/sample-north-london.ts";

const profile = {
  ...SAMPLE_NORTH_LONDON_PROFILE,
  id: "09b10c29-fc48-4c4e-97c7-da5e010cdf69",
  updated_at: "2026-06-01T00:00:00.000001Z",
  is_synthetic_sample: false,
};
const settings = {
  ayanamsha: "lahiri",
  node_type: "mean",
  house_system: "whole_sign",
  year_days: 365.25,
  preset: null,
};
const envelope = {
  profile_id: profile.id,
  profile_updated_at: profile.updated_at,
  input_calendar: "AD",
  time_certainty: "exact",
  chart: {
    chart_id: "opaque-id",
    engine_version: "0.2.0",
    settings,
    metadata: { ephemeris_source: "mixed" },
    facts: [],
  },
};

describe("Chart calculation API", () => {
  it("POSTs supported defaults only and preserves the response envelope", async () => {
    const result = await calculateChart({
      getAccessToken: () => "sample-token",
      baseUrl: "https://kundali.invalid/api/v1/",
      fetchImpl: async (url, init) => {
        assert.equal(url, `https://kundali.invalid/api/v1/profiles/${profile.id}/chart`);
        assert.equal(init.method, "POST");
        assert.equal(init.headers.Authorization, "Bearer sample-token");
        assert.equal(init.credentials, "omit");
        assert.equal(init.cache, "no-store");
        assert.deepEqual(JSON.parse(init.body), {
          ayanamsha: "lahiri", node_type: "mean", house_system: "whole_sign", year_days: 365.25,
        });
        return Response.json(envelope);
      },
    }, profile, { ...settings, date_ad: profile.date_ad });
    assert.deepEqual(result, envelope);
    assert.equal(getProvenanceStatus(result.chart, "ready"), "mixed");
  });

  it("delegates preset defaults to the backend and preserves a year length override", async () => {
    const resolved = { ...settings, ayanamsha: "lahiri_1940", node_type: "true",
      preset: "hamro_patro_compat", year_days: 360 };
    const result = await calculateChart({
      getAccessToken: () => "sample-token",
      fetchImpl: async (_url, init) => {
        assert.deepEqual(JSON.parse(init.body), { preset: "hamro_patro_compat", year_days: 360 });
        return Response.json({ ...envelope, chart: { ...envelope.chart, settings: resolved } });
      },
    }, profile, { ...settings, preset: "hamro_patro_compat", year_days: 360 });
    assert.deepEqual(result.chart.settings, resolved);
  });

  it("matches the source revision and certainty independently of chart_id", () => {
    assert.ok(matchesChartProfile(envelope, profile));
    assert.ok(!matchesChartProfile(envelope, { ...profile, id: "different" }));
    assert.ok(!matchesChartProfile(envelope, {
      ...profile, updated_at: "2026-06-01T00:00:00.000002Z",
    }));
    assert.ok(!matchesChartProfile(envelope, { ...profile, time_certainty: "approximate" }));
    assert.ok(!matchesChartProfile(envelope, { ...profile, input_calendar: "BS" }));
  });

  it("blocks sample and unpersisted profiles before fetching", () => {
    for (const input of [SAMPLE_NORTH_LONDON_PROFILE,
      { ...profile, id: SAMPLE_NORTH_LONDON_PROFILE.id },
      { ...profile, updated_at: undefined }]) {
      assert.throws(() => calculateChart({
        fetchImpl: () => assert.fail("must not fetch"),
      }, input, settings), (error) => getChartIssue(error) === "validation");
    }
  });

  it("maps structured conflicts and HTTP failures to presentation keys", async () => {
    for (const [status, code, issue] of [
      [409, "AWAITING_BS_CONVERSION", "bsPending"],
      [409, "UNKNOWN_TIME_UNSUPPORTED", "unknownTime"],
      [409, "INCOMPLETE_BIRTH_DATA", "incomplete"],
      [409, "CHART_DATE_OUT_OF_RANGE", "dateRange"],
      [403, null, "forbidden"],
      [404, null, "missing"],
      [422, "dst_overlap", "validation"],
      [500, null, "server"],
    ]) {
      await assert.rejects(calculateChart({
        getAccessToken: () => "sample-token",
        fetchImpl: async () => Response.json({ code, detail: "private diagnostic" }, { status }),
      }, profile, settings), (error) => getChartIssue(error) === issue);
    }
    await assert.rejects(calculateChart({
      getAccessToken: () => "sample-token",
      fetchImpl: async () => { throw new TypeError("failed fetch"); },
    }, profile, settings), (error) => getChartIssue(error) === "network");
  });

  it("retries chart authentication once and surfaces a final 401", async () => {
    const authHeaders = [];
    let refreshes = 0;
    await assert.rejects(calculateChart({
      getAccessToken: () => "expired-token",
      onUnauthorizedRefresh: async (token) => {
        assert.equal(token, "expired-token");
        refreshes++;
        return "refreshed-token";
      },
      fetchImpl: async (_url, init) => {
        authHeaders.push(init.headers.Authorization);
        return Response.json({}, { status: 401 });
      },
    }, profile, settings), (error) => getChartIssue(error) === "auth");
    assert.equal(refreshes, 1);
    assert.deepEqual(authHeaders, ["Bearer expired-token", "Bearer refreshed-token"]);
  });
});
