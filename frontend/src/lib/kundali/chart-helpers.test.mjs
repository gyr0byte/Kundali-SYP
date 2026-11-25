import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildAllowlistedLlmPayload,
  classifySettingsChange,
  formatDegreeInSign,
  getProvenanceStatus,
  getWholeSignHouseMap,
  isUnknownTimeProfile,
} from "./chart-helpers.ts";
import {
  SAMPLE_NORTH_LONDON_CHART_FACTS,
  SAMPLE_NORTH_LONDON_PROFILE,
} from "./sample-north-london.ts";

describe("ChartFacts provenance and schema invariants", () => {
  it("uses deterministic North London snapshot with verified swieph metadata", () => {
    assert.equal(SAMPLE_NORTH_LONDON_CHART_FACTS.chart_id, "sample_north_london");
    assert.equal(SAMPLE_NORTH_LONDON_CHART_FACTS.settings.house_system, "whole_sign");
    assert.equal(SAMPLE_NORTH_LONDON_CHART_FACTS.metadata.ephemeris_source, "swieph");
    assert.equal(SAMPLE_NORTH_LONDON_CHART_FACTS.facts.length, 10);

    for (const fact of SAMPLE_NORTH_LONDON_CHART_FACTS.facts) {
      assert.equal("dignity" in fact, false);
      assert.equal("ephemeris_source" in fact, false);
      assert.equal("ayanamsha" in fact, false);
    }
  });

  it("never displays unverified or non-ready states as verified", () => {
    assert.equal(getProvenanceStatus(SAMPLE_NORTH_LONDON_CHART_FACTS, "ready"), "swieph");
    assert.equal(getProvenanceStatus(SAMPLE_NORTH_LONDON_CHART_FACTS, "awaiting_recompute"), "unknown");
    assert.equal(getProvenanceStatus(SAMPLE_NORTH_LONDON_CHART_FACTS, "awaiting_bs_conversion"), "unknown");
    assert.equal(getProvenanceStatus(SAMPLE_NORTH_LONDON_CHART_FACTS, "unknown_time_unimplemented"), "unknown");
    assert.equal(getProvenanceStatus(null, "ready"), "unknown");
  });
});

describe("LLM privacy allowlist boundary", () => {
  it("strips ChartMetadata timestamps, Julian Day, offsets, and chart identifiers", () => {
    const payload = buildAllowlistedLlmPayload(SAMPLE_NORTH_LONDON_CHART_FACTS, ["f_lagna", "f_moon"]);
    const serialized = JSON.stringify(payload);

    assert.equal(payload.facts.length, 2);
    assert.equal(serialized.includes("datetime_utc_iso"), false);
    assert.equal(serialized.includes("julian_day"), false);
    assert.equal(serialized.includes("utc_offset_hours"), false);
    assert.equal(serialized.includes("2457158.0625"), false);
    assert.equal(serialized.includes("2015-05-15T13:30:00+00:00"), false);
    assert.equal(serialized.includes("sample_north_london"), false);
    assert.deepEqual(payload.conventions, {
      ayanamsha: "lahiri",
      node_type: "mean",
      house_system: "whole_sign",
      year_days: 365.25,
    });
  });
});

describe("Scoped calculation settings changes", () => {
  const base = {
    ayanamsha: "lahiri",
    house_system: "whole_sign",
    node_type: "mean",
    year_days: 365.25,
    preset: null,
  };

  it("classifies year_days-only edits as dasha_only without planetary recompute", () => {
    assert.equal(classifySettingsChange(base, { ...base, year_days: 360 }), "dasha_only");
  });

  it("classifies ayanamsha, node_type, or preset edits as full_chart", () => {
    assert.equal(classifySettingsChange(base, { ...base, ayanamsha: "lahiri_1940" }), "full_chart");
    assert.equal(classifySettingsChange(base, { ...base, node_type: "true" }), "full_chart");
    assert.equal(
      classifySettingsChange(base, { ...base, preset: "hamro_patro_compat" }),
      "full_chart"
    );
  });

  it("returns none when staged settings match applied settings", () => {
    assert.equal(classifySettingsChange(base, { ...base }), "none");
  });
});

describe("Calendar separation, unknown time, and Whole Sign house mapping", () => {
  it("keeps original input calendar separate and detects unknown time certainty", () => {
    const unknownBsProfile = {
      ...SAMPLE_NORTH_LONDON_PROFILE,
      id: "bs_unknown",
      input_calendar: "BS",
      entered_date: "2055-04-15",
      date_ad: null,
      time_local: null,
      time_certainty: "unknown",
    };
    assert.equal(isUnknownTimeProfile(unknownBsProfile), true);
    assert.equal(unknownBsProfile.time_local, null);
    assert.equal(unknownBsProfile.input_calendar, "BS");
  });

  it("maps Whole Sign houses cyclically from Lagna sign index", () => {
    assert.deepEqual(getWholeSignHouseMap(4), [4, 5, 6, 7, 8, 9, 10, 11, 0, 1, 2, 3]);
  });

  it("formats degrees in sign cleanly", () => {
    assert.equal(formatDegreeInSign(25.587919), "25°35′");
    assert.equal(formatDegreeInSign(0.336599), "00°20′");
  });
});
