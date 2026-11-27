import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { astrologerIssue, submitAstrologerApplication, validateApplication, verifyReviewAccess } from "./astrologer.ts";

const form = { display_name: "  Asha  ", credentials: " Ten years of practice ", tradition: " Vedic " };
const profile = { display_name: "Asha", credentials: "Ten years of practice", tradition: "Vedic" };
const config = (fetchImpl) => ({ baseUrl: "http://api.test/api/v1", getAccessToken: () => "test-access", fetchImpl });

test("validates trimmed application fields against the backend length limits", () => {
  assert.deepEqual(validateApplication(form), {
    payload: profile, errors: { display_name: false, credentials: false, tradition: false },
  });
  assert.deepEqual(validateApplication({ display_name: "  अ ", tradition: "अ".repeat(101), credentials: " short " }).errors,
    { display_name: true, credentials: true, tradition: true });
});

test("submits the allowlisted application and returns only the caller's pending credentials", async () => {
  const result = await submitAstrologerApplication(config(async (url, request) => {
    assert.equal(url, "http://api.test/api/v1/astrologer/apply");
    assert.equal(request.method, "POST");
    assert.equal(request.headers.Authorization, "Bearer test-access");
    assert.equal(request.cache, "no-store");
    assert.deepEqual(JSON.parse(request.body), profile);
    return Response.json({ ...profile, user_id: "self", status: "pending", approved_by: null }, { status: 201 });
  }), "self", { ...form, user_id: "injected" });
  assert.deepEqual(result, profile);
  await assert.rejects(submitAstrologerApplication(config(() =>
    Response.json({ ...profile, user_id: "other", status: "pending" })), "self", form), /Unexpected/);
});

test("distinguishes duplicate applications from errors without interpreting unsupported status", async () => {
  for (const [status, detail, issue] of [
    [400, "Application already submitted", "duplicate"],
    [400, "User not found", "unavailable"],
    [422, [], "validation"],
  ]) {
    await assert.rejects(submitAstrologerApplication(config(() =>
      Response.json({ detail }, { status })), "self", form), (error) => astrologerIssue(error) === issue);
  }
});

test("review authorization accepts the empty stub and discards all unrecognized records", async () => {
  await verifyReviewAccess(config((url, request) => {
    assert.equal(url, "http://api.test/api/v1/review/queue");
    assert.equal(request.method, "GET");
    return Response.json([]);
  }));
  await assert.rejects(verifyReviewAccess(config(() =>
    Response.json([{ raw_birth_data: "unexpected" }]))), /supported empty stub/);
  await assert.rejects(verifyReviewAccess(config(() =>
    Response.json({ detail: "Approved astrologer or administrator access required" }, { status: 403 }))),
  (error) => astrologerIssue(error) === "forbidden");
});

test("queue requests require authentication and reuse the existing one-shot refresh", async () => {
  await assert.rejects(verifyReviewAccess({ fetchImpl: () => assert.fail("sent without authentication") }),
    (error) => astrologerIssue(error) === "auth");
  const calls = [];
  await verifyReviewAccess({
    ...config((_url, request) => {
      calls.push(request.headers.Authorization);
      return calls.length === 1 ? Response.json({}, { status: 401 }) : Response.json([]);
    }),
    onUnauthorizedRefresh: async () => "renewed",
  });
  assert.deepEqual(calls, ["Bearer test-access", "Bearer renewed"]);
});

test("astrologer dictionaries contain the same message keys", async () => {
  const keys = async (locale) => Object.keys(JSON.parse(await readFile(
    new URL(`../../i18n/astrologer.${locale}.json`, import.meta.url), "utf8"
  ))).sort();
  assert.deepEqual(await keys("en"), await keys("ne"));
});
