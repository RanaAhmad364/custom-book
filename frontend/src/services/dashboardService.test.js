import assert from "node:assert/strict";
import test from "node:test";
import { loadDashboardData } from "../features/dashboard/dashboardService.js";

test("dashboard data is composed from authenticated API resources", async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  const responses = {
    "/projects": { items: [{ id: "project-1", title: "My saved book", status: "draft", pageCount: 24, version: 1 }] },
    "/print/orders": { items: [{
      id: "order-1",
      orderNumber: "PRT-101",
      productionStatus: "shipped",
      paymentStatus: "successful",
      amount: "6500.00",
      currency: "PKR",
      createdAt: "2026-10-01T00:00:00Z",
      trackingNumber: "TRACK-101",
    }] },
    "/pdf/orders": { items: [{
      id: "pdf-1",
      title: "Family memories",
      paymentStatus: "successful",
      generationStatus: "ready",
      downloadId: "entitlement-1",
      pageCount: 24,
      createdAt: "2026-10-02T00:00:00Z",
    }] },
    "/payments/notifications": { items: [{
      id: "notice-1",
      category: "order",
      title: "Order shipped",
      message: "Your order has shipped.",
      readAt: null,
      createdAt: "2026-10-03T00:00:00Z",
    }] },
    "/auth/me/addresses": { items: [{
      id: "address-1",
      recipientName: "Memory Member",
      addressLine1: "1 Book Street",
      city: "Lahore",
      postalCode: "54000",
      countryCode: "PK",
    }] },
    "/auth/me/notification-preferences": { items: [
      { channel: "email", category: "order", enabled: true },
      { channel: "email", category: "product_news", enabled: false },
    ] },
  };

  globalThis.fetch = async (url) => {
    const path = new URL(url, "http://localhost").pathname.replace("/api/v1", "");
    requests.push(path);
    if (!(path in responses)) throw new Error(`Unexpected dashboard request: ${path}`);
    return new Response(JSON.stringify(responses[path]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const dashboard = await loadDashboardData({ email: "member@example.test", name: "Memory Member", phone: "03001234567" });
    assert.deepEqual(new Set(requests), new Set(Object.keys(responses)));
    assert.equal(dashboard.profile.name, "Memory Member");
    assert.equal(dashboard.projects[0].title, "My saved book");
    assert.equal(dashboard.projects[0].pages, 24);
    assert.equal(dashboard.orders[0].status, "Shipped");
    assert.equal(dashboard.orders[0].reference, "PRT-101");
    assert.equal(dashboard.downloads[0].status, "Ready");
    assert.equal(dashboard.notifications[0].read, false);
    assert.equal(dashboard.addresses[0].countryCode, "PK");
    assert.deepEqual(dashboard.settings, { orderEmails: true, productNews: false });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("dashboard loading rejects malformed service data instead of showing sample activity", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const path = new URL(url, "http://localhost").pathname.replace("/api/v1", "");
    const payload = path === "/print/orders" ? { items: null } : { items: [] };
    return new Response(JSON.stringify(payload), { status: 200 });
  };
  try {
    await assert.rejects(
      loadDashboardData({ email: "member@example.test", name: "Member" }),
      /invalid response/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
