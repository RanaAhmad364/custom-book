import assert from "node:assert/strict";
import test from "node:test";
import { normalizeOrderTimeline, orderTimelineLabel } from "./orderTimeline.js";

test("timeline labels customer-facing print milestones", () => {
  assert.equal(orderTimelineLabel("pending_payment"), "Placed");
  assert.equal(orderTimelineLabel("payment_confirmed"), "Payment confirmed");
  assert.equal(orderTimelineLabel("out_for_delivery"), "Out for delivery");
});

test("timeline keeps valid history entries and orders them chronologically", () => {
  const timeline = normalizeOrderTimeline([
    { status: "shipped", createdAt: "2026-03-03T10:00:00+00:00" },
    { status: "payment_confirmed", createdAt: "2026-03-01T10:00:00+00:00" },
    { status: "invalid" },
  ]);
  assert.deepEqual(timeline.map((item) => item.status), ["payment_confirmed", "shipped"]);
  assert.ok(timeline.every((item) => item.id));
});
