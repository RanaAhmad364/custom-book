import test from "node:test";
import assert from "node:assert/strict";
import { buildAdminHistoryQuery } from "./adminHistory.js";

test("admin history query serializes supported filters and omits empty values", () => {
  const query = buildAdminHistoryQuery({
    search: "  receipt  ",
    dateFrom: "2026-10-01",
    dateTo: "",
    type: "print",
    page: 4,
    status: "shipped",
  });

  assert.equal(
    query,
    "search=receipt&dateFrom=2026-10-01&status=shipped&type=print",
  );
});

test("admin history query encodes customer and book filters", () => {
  const query = buildAdminHistoryQuery({ user: "A Person+1@example.test", book: "Autumn & Home" });
  const parsed = new URLSearchParams(query);
  assert.equal(parsed.get("user"), "A Person+1@example.test");
  assert.equal(parsed.get("book"), "Autumn & Home");
});
