import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { adminIssue, fetchAdminRecords, fetchAdminTotals, submitAdminAction } from "./admin.ts";

const id = "11111111-1111-4111-8111-111111111111";
const config = (fetchImpl) => ({ getAccessToken: () => "test-access", fetchImpl, baseUrl: "http://admin.test" });
const page = (items = [], total = 0, limit = 20, offset = 0) => ({ items, total, limit, offset });

test("sends only supported filters and pagination on each collection", async () => {
  const cases = [
    [{ section: "users", role: "admin", active: false }, "/admin/users?limit=20&offset=40&role=admin&is_active=false"],
    [{ section: "astrologers", status: "pending" }, "/admin/astrologers?limit=20&offset=40&status=pending"],
    [{ section: "audit" }, "/admin/audit?limit=20&offset=40"],
  ];
  for (const [query, path] of cases) {
    const result = await fetchAdminRecords(config((url, init) => {
      assert.equal(url, "http://admin.test" + path);
      assert.equal(init.cache, "no-store");
      return Response.json(page([], 45, 20, 40));
    }), query, 20, 40);
    assert.equal(result.page.total, 45);
  }
});

test("projects audit fields and removes arbitrary metadata, private references and unknown event text", async () => {
  const records = await fetchAdminRecords(config(() => Response.json(page([{
    id, actor_id: id, created_at: "2026-01-01T00:00:00Z", action: "raw private input",
    target_type: "birth_profile", target_id: id, ip: "private IP", metadata: { birth_date: "private date" },
  }], 1))), { section: "audit" }, 20, 0);
  assert.deepEqual(records.page.items[0], {
    id, actor_id: id, created_at: "2026-01-01T00:00:00Z", action: "other", target_type: "birth_profile", target_id: null,
  });
});

test("omits astrologer application free text and uses backend totals independently of row count", async () => {
  const records = await fetchAdminRecords(config(() => Response.json(page([{
    user_id: id, display_name: "Reviewer", tradition: "Vedic", status: "pending", credentials: "private",
  }], 1))), { section: "astrologers" }, 20, 0);
  assert.ok(!Object.hasOwn(records.page.items[0], "credentials"));
  const totals = await fetchAdminTotals(config((value) => {
    const url = new URL(value);
    assert.equal(url.searchParams.get("limit"), "1");
    if (url.pathname.endsWith("/astrologers")) assert.equal(url.searchParams.get("status"), "pending");
    return Response.json(page([], { users: 44, astrologers: 16, audit: 91 }[url.pathname.split("/").at(-1)], 1));
  }));
  assert.deepEqual(totals, [44, 16, 91]);
});

test("all mutations use POST and accept empty 204 responses", async () => {
  for (const [action, group] of [["deactivate", "users"], ["reactivate", "users"], ["approve", "astrologers"], ["suspend", "astrologers"]]) {
    await submitAdminAction(config((url, init) => {
      assert.equal(url, `http://admin.test/admin/${group}/${id}/${action}`);
      assert.equal(init.method, "POST");
      assert.equal(init.body, undefined);
      return new Response(null, { status: 204 });
    }), action, id);
  }
});

test("maps backend protections and stale records without releasing exception text", async () => {
  for (const [status, detail, issue] of [
    [400, "Cannot deactivate your own account", "protected"],
    [400, "Cannot deactivate the last admin", "protected"],
    [404, "User not found", "stale"],
    [403, "Insufficient permissions", "forbidden"],
    [401, "Expired token", "expired"],
    [500, "private detail", "failed"],
  ]) {
    await assert.rejects(submitAdminAction(config(() => Response.json({ detail }, { status })), "deactivate", id),
      (error) => adminIssue(error) === issue);
  }
});

test("admin dictionaries contain the same message keys", async () => {
  const keys = async (locale) => Object.keys(JSON.parse(await readFile(
    new URL(`../../i18n/admin.${locale}.json`, import.meta.url), "utf8"
  ))).sort();
  assert.deepEqual(await keys("en"), await keys("ne"));
});
