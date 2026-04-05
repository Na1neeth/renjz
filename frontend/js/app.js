const STORAGE_TOKEN = "renjis_token";
const STORAGE_USER = "renjis_user";

const state = {
  token: localStorage.getItem(STORAGE_TOKEN) || "",
  user: readJson(localStorage.getItem(STORAGE_USER)),
  tables: [],
  selectedTableId: null,
  selectedTable: null,
  selectedSeatNumbers: [],
  pendingBills: [],
  selectedReceptionOrderId: null,
  selectedReceptionOrder: null,
  billing: null,
  kitchenTables: [],
  socket: null,
  notice: "",
  error: "",
  busy: "",
  flashes: {},
};

const demoUsers = [
  { role: "waiter", username: "waiter", password: "demo123" },
  { role: "kitchen", username: "kitchen", password: "demo123" },
  { role: "receptionist", username: "reception", password: "demo123" },
];

const FLOOR_LAYOUT = [
  { key: "A", tableNames: ["A1", "A2", "A3", "A4"] },
  { key: "B", tableNames: ["B1", "B2", "B3", "B4", "B5"] },
  { key: "C", tableNames: ["C1", "C2", "C3", "C4"] },
];

const TABLE_LABELS_BY_INDEX = {
  1: "A1",
  2: "A2",
  3: "A3",
  4: "A4",
  5: "B1",
  6: "B2",
  7: "B3",
  8: "B4",
  9: "B5",
  10: "C1",
  11: "C2",
  12: "C3",
  13: "C4",
};

const app = document.querySelector("#app");

boot();

async function boot() {
  render();
  if (!state.token) {
    return;
  }

  try {
    state.busy = "Restoring session";
    state.user = await api("/auth/me");
    persistSession();
    connectSocket();
    await refreshRoleData();
  } catch (error) {
    clearSession();
    state.error = "Previous session expired. Please sign in again.";
  } finally {
    state.busy = "";
    render();
  }
}

function render() {
  app.innerHTML = state.user ? renderDashboard() : renderLogin();
  bindCommonEvents();
  if (!state.user) {
    bindLoginEvents();
    return;
  }

  if (state.user.role === "waiter") {
    bindWaiterEvents();
  }
  if (state.user.role === "kitchen") {
    bindKitchenEvents();
  }
  if (state.user.role === "receptionist") {
    bindReceptionEvents();
  }
}

function renderLogin() {
  return `
    <div class="login-shell">
      <div class="login-card">
        <section class="hero-panel">
          <div class="eyebrow">Restaurant MVP</div>
          <h1 class="hero-title">Renjz Kitchen service board</h1>
          <p class="hero-copy">
            Free-text ordering for the floor, live handoff to the kitchen, and manual pricing at checkout for reception.
          </p>
          <div class="demo-grid">
            ${demoUsers
              .map(
                (user) => `
                  <div class="demo-card">
                    <strong>${capitalize(user.role)}</strong>
                    <p>${user.username} / ${user.password}</p>
                    <div class="footer-note">Tap the preset to fill the form instantly.</div>
                  </div>
                `,
              )
              .join("")}
          </div>
        </section>
        <section class="form-panel">
          <h2 class="section-title">Sign in</h2>
          <p class="muted">Choose one of the seeded users or enter credentials manually.</p>
          ${state.error ? `<div class="error-strip">${escapeHtml(state.error)}</div>` : ""}
          <form id="login-form" class="login-form">
            <div class="field-grid">
              <label class="label" for="username">Username</label>
              <input id="username" class="input" name="username" autocomplete="username" required />
            </div>
            <div class="field-grid">
              <label class="label" for="password">Password</label>
              <input id="password" class="input" name="password" type="password" autocomplete="current-password" required />
            </div>
            <div class="action-row">
              <button class="primary-btn" type="submit">${state.busy || "Sign in"}</button>
            </div>
          </form>
          <div class="demo-grid">
            ${demoUsers
              .map(
                (user) => `
                  <button class="ghost-btn demo-fill-btn" data-username="${user.username}" data-password="${user.password}">
                    Use ${capitalize(user.role)}
                  </button>
                `,
              )
              .join("")}
          </div>
        </section>
      </div>
    </div>
  `;
}

function renderDashboard() {
  return `
    <div class="app-shell">
      <header class="topbar">
        <div class="brand-block">
          <div class="eyebrow">${capitalize(state.user.role)} workspace</div>
          <h1 class="app-title">Renjz Kitchen</h1>
          <div class="muted">${escapeHtml(state.user.display_name)} is signed in as ${capitalize(state.user.role)}.</div>
        </div>
        <div class="topbar-actions">
          ${state.notice ? `<div class="notice-strip">${escapeHtml(state.notice)}</div>` : ""}
          ${state.error ? `<div class="error-strip">${escapeHtml(state.error)}</div>` : ""}
          ${state.busy ? `<div class="stat-pill"><strong>Working</strong><span>${escapeHtml(state.busy)}</span></div>` : ""}
          <div class="topbar-metrics">
            <div class="stat-pill">
              <strong>Live updates</strong>
              <span>${state.socket && state.socket.readyState === WebSocket.OPEN ? "Connected" : "Reconnecting"}</span>
            </div>
            <div class="compact-actions">
              <button class="ghost-btn" id="refresh-view">Refresh</button>
              <button class="secondary-btn" id="logout-btn">Log out</button>
            </div>
          </div>
        </div>
      </header>
      ${renderRoleView()}
    </div>
  `;
}

function renderRoleView() {
  if (state.user.role === "waiter") {
    return renderWaiterView();
  }
  if (state.user.role === "kitchen") {
    return renderKitchenView();
  }
  return renderReceptionView();
}

function renderWaiterView() {
  const table = state.selectedTable;
  const activeOrders = table?.active_orders || [];
  return `
    <main class="view-grid service-layout">
      <section class="panel">
        <h2 class="panel-title">Tables</h2>
        <p class="muted">Floor view matches the restaurant top view: A has 4 tables, B has 5, and C has 4.</p>
        ${renderTableLayout()}
      </section>
      <section class="table-detail-card service-detail-panel" id="table-detail-panel">
        ${
          table
            ? `
            <div class="badge-row">
              ${renderBadge(table.status)}
              <span class="badge running">${table.active_orders_count} checks</span>
              ${table.pending_bills_count ? `<span class="badge billing">${table.pending_bills_count} pending</span>` : ""}
            </div>
            <h2 class="panel-title" style="margin-top: 14px;">${escapeHtml(table.name)}</h2>
            <div class="meta-stack">
              <span>Seat capacity: ${table.seat_count}</span>
              <span>Live checks: ${table.active_orders_count}</span>
              <span>Active items: ${table.active_items_count}</span>
              <span>Ready from kitchen: ${table.ready_items_count}</span>
              <span>Pending bills at reception: ${table.pending_bills_count}</span>
              <span>Last activity: ${formatDateTime(table.last_activity_at)}</span>
            </div>
            ${
              table.status === "empty"
                ? renderWaiterEmptyState(table)
                : `
                ${renderSeatPlanner(table)}
                ${
                  activeOrders.length
                    ? activeOrders.map((order) => renderWaiterCheckCard(order)).join("")
                    : `
                      <div class="empty-box" style="margin-top: 18px;">
                        <h3 class="section-title">No live checks yet</h3>
                        <p class="muted">
                          ${
                            getAvailableSeats(table).length
                              ? "Select one or more free seats above to start a check."
                              : "Every seat in this table cycle is already attached to a bill or closed check."
                          }
                        </p>
                      </div>
                    `
                }
                ${
                  !activeOrders.length
                    ? `
                      <div class="empty-box" style="margin-top: 18px;">
                        <h3 class="section-title">Floor release</h3>
                        <p class="muted">Mark the table empty only after everyone at this table has physically left.</p>
                        <button class="primary-btn" id="mark-empty-btn" data-table-id="${table.id}">Mark table empty</button>
                      </div>
                    `
                    : ""
                }
              `
            }
          `
            : `<div class="empty-box"><p class="muted">No table selected.</p></div>`
        }
      </section>
    </main>
  `;
}

function renderKitchenView() {
  return `
    <main class="view-grid">
      <section class="panel">
        <h2 class="panel-title">Kitchen dashboard</h2>
        <p class="muted">Simple kitchen queue for phone use. Only new and ready are used here.</p>
      </section>
      <section class="kitchen-grid">
        ${
          state.kitchenTables.length
            ? state.kitchenTables
                .map((table) => {
                  const entries = table.active_orders.flatMap((order) =>
                    order.items.map((item) => ({ order, item })),
                  );
                  const activeItems = entries.filter((entry) => entry.item.item_status === "active");
                  const cancelledItems = entries.filter((entry) => entry.item.item_status === "cancelled");
                  const latestUpdate = table.active_orders.reduce((latest, order) => {
                    if (!latest) {
                      return order.updated_at;
                    }
                    return new Date(order.updated_at) > new Date(latest) ? order.updated_at : latest;
                  }, null);
                  return `
                    <article class="order-box kitchen-table-card">
                      <div class="badge-row">
                        <span class="badge running">${escapeHtml(table.name)}</span>
                        <span class="badge billing">${table.active_orders_count} checks</span>
                        <span class="badge ready">${table.ready_items_count} ready</span>
                      </div>
                      <h3 class="section-title" style="margin-top: 12px;">${table.active_items_count} active portions</h3>
                      <div class="meta-stack kitchen-meta">
                        <span>Updated: ${formatDateTime(latestUpdate)}</span>
                        ${cancelledItems.length ? `<span>${cancelledItems.length} cancelled</span>` : ""}
                      </div>
                      <div class="item-list" style="margin-top: 16px;">
                        ${activeItems.map((entry) => renderKitchenItemCard(entry.order, entry.item)).join("")}
                        ${cancelledItems.map((entry) => renderKitchenItemCard(entry.order, entry.item)).join("")}
                      </div>
                    </article>
                  `;
                })
                .join("")
            : `<div class="empty-box"><h3 class="section-title">No active tables</h3><p class="muted">The kitchen queue is currently clear.</p></div>`
        }
      </section>
    </main>
  `;
}

function renderReceptionView() {
  const table = state.selectedTable;
  const runningOrders = table?.active_orders || [];
  const billingOrder = state.selectedReceptionOrder;
  const billing = state.billing;
  const pendingBillsForTable = table ? getPendingBillsForTable(table.id) : [];
  return `
    <main class="view-grid service-layout">
      <section class="panel">
        <h2 class="panel-title">Tables</h2>
        <p class="muted">Floor view matches the restaurant top view so reception sees the same layout as service.</p>
        ${renderTableLayout()}
      </section>
      <section class="view-grid service-detail-stack">
        ${
          table
            ? `
            <section class="table-detail-card service-detail-panel" id="table-detail-panel">
              <div class="badge-row">
                ${renderBadge(table.status)}
                ${runningOrders.length ? `<span class="badge running">${runningOrders.length} live checks</span>` : ""}
                ${table.pending_bills_count ? `<span class="badge billing">${table.pending_bills_count} pending</span>` : ""}
              </div>
              <h2 class="panel-title" style="margin-top: 14px;">${escapeHtml(table.name)}</h2>
              <div class="meta-stack">
                <span>Seat capacity: ${table.seat_count}</span>
                <span>Live checks: ${table.active_orders_count}</span>
                <span>Active items: ${table.active_items_count}</span>
                <span>Ready from kitchen: ${table.ready_items_count}</span>
                <span>Pending bills at reception: ${table.pending_bills_count}</span>
                <span>Last activity: ${formatDateTime(table.last_activity_at)}</span>
              </div>
              ${
                runningOrders.length
                  ? `
                    <div class="item-list" style="margin-top: 16px;">
                      ${runningOrders.map(renderReceptionLiveCheckCard).join("")}
                    </div>
                    <div class="status-banner info" style="margin-top: 16px;">
                      ${
                        pendingBillsForTable.length
                          ? "Waiter is still serving this table, and one or more older seat checks from the same table are already waiting in the queue below."
                          : "Waiter is still serving this table. Each seat check will appear in the billing queue separately after the waiter sends it."
                      }
                    </div>
                  `
                  : `
                    <div class="status-banner info" style="margin-top: 16px;">
                      ${renderReceptionTableNotice(table)}
                    </div>
                  `
              }
            </section>
          `
            : ""
        }
        <section class="panel">
          <div class="split-header">
            <div>
              <h3 class="section-title">Pending bills</h3>
              <p class="muted">Reception can settle old bills even if the waiter has already reopened the table.</p>
            </div>
            <span class="badge billing">${state.pendingBills.length} open</span>
          </div>
          <div class="pending-bills-list" style="margin-top: 16px;">
            ${
              state.pendingBills.length
                ? state.pendingBills.map(renderPendingBillCard).join("")
                : `<div class="empty-box"><h3 class="section-title">No pending bills</h3><p class="muted">Orders moved to billing will appear here until payment is completed.</p></div>`
            }
          </div>
        </section>
        ${
          billingOrder && billing
            ? `
            <section class="billing-box">
              <div class="split-header">
                <div>
                  <h3 class="section-title">Manual billing</h3>
                  <p class="muted">${escapeHtml(billing.table_name)} · ${escapeHtml(billing.seat_label)} · Check ${billingOrder.id} · ${capitalize(billingOrder.status)}</p>
                </div>
                <span class="badge billing">${escapeHtml(billing.seat_label)}</span>
              </div>
              <form id="billing-form">
                <div class="billing-grid">
                  <div class="span-12">
                    <table class="billing-table">
                      <thead>
                        <tr>
                          <th>Item</th>
                          <th>Consumed</th>
                          <th>Bill Qty</th>
                          <th>Unit Price</th>
                          <th>Include</th>
                          <th>Line total</th>
                        </tr>
                      </thead>
                      <tbody>
                        ${billing.items.map((item, index) => renderBillingRow(item, index)).join("")}
                      </tbody>
                    </table>
                  </div>
                  <div class="field-grid span-3">
                    <label class="label" for="discount">Discount</label>
                    <input class="input" id="discount" name="discount" type="number" min="0" step="0.01" value="${formatNumber(billing.discount)}" />
                  </div>
                  <div class="field-grid span-4">
                    <label class="label" for="payment_method">Payment method</label>
                    <select class="select" id="payment_method" name="payment_method">
                      <option value="cash">Cash</option>
                      <option value="card">Card</option>
                      <option value="upi">UPI</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <div class="field-grid span-5">
                    <label class="label" for="payment_notes">Payment notes</label>
                    <input class="input" id="payment_notes" name="payment_notes" placeholder="Optional internal note" />
                  </div>
                </div>
                <div class="totals-box">
                  <div class="totals-line"><span>Subtotal</span><strong id="subtotal-value">${moneyLabel(billing.subtotal)}</strong></div>
                  <div class="totals-line"><span>Discount</span><strong id="discount-value">${moneyLabel(billing.discount)}</strong></div>
                  <div class="totals-line strong"><span>Final total</span><strong id="final-total-value">${moneyLabel(billing.final_total)}</strong></div>
                </div>
                <div class="action-row" style="margin-top: 16px;">
                  <button class="primary-btn" type="button" id="save-billing-btn" data-order-id="${billingOrder.id}">Save bill draft</button>
                  <button class="secondary-btn" type="button" id="checkout-btn" data-order-id="${billingOrder.id}">Mark payment complete</button>
                </div>
              </form>
            </section>
            <section class="history-box">
              <h3 class="section-title">Activity log</h3>
              <div class="history-list">
                ${billingOrder.activity_log.length ? billingOrder.activity_log.map(renderHistoryRow).join("") : `<div class="empty-box"><p class="muted">No activity yet.</p></div>`}
              </div>
            </section>
          `
            : `
            <section class="empty-box">
              <h3 class="section-title">Select a pending bill</h3>
              <p class="muted">
                ${
                  state.pendingBills.length
                    ? "Choose a bill from the reception queue to price items, apply discounts, and complete payment."
                    : "No orders are waiting for billing right now."
                }
              </p>
            </section>
          `
        }
      </section>
    </main>
  `;
}

function renderTableButton(table, active) {
  return `
    <button class="table-button ${active ? "active" : ""}" data-table-id="${table.id}">
      <div class="badge-row">
        <span class="badge ${table.status}">${escapeHtml(displayStatus(table.status))}</span>
        ${table.pending_bills_count ? `<span class="badge billing">${table.pending_bills_count} bill</span>` : ""}
      </div>
      <h4>${escapeHtml(table.name)}</h4>
      <div class="meta-stack">
        <span>Checks: ${table.active_orders_count}</span>
        <span>Items: ${table.active_items_count}</span>
        <span>Ready: ${table.ready_items_count}</span>
        <span>Pending: ${table.pending_bills_count}</span>
      </div>
    </button>
  `;
}

function renderTableLayout() {
  return `
    <div class="table-layout-wrap">
      <div class="table-layout">
      ${FLOOR_LAYOUT.map((column) => renderTableColumn(column)).join("")}
      </div>
    </div>
  `;
}

function renderTableColumn(column) {
  return `
    <section class="table-column">
      <div class="table-column-head">
        <span class="table-column-badge">${escapeHtml(column.key)}</span>
        <div>
          <h3 class="section-title">Lane ${escapeHtml(column.key)}</h3>
          <p class="muted">${column.tableNames.length} tables</p>
        </div>
      </div>
      <div class="table-stack">
        ${column.tableNames.map((tableName) => renderTableSlot(tableName)).join("")}
      </div>
    </section>
  `;
}

function renderTableSlot(tableName) {
  const table = getTableByName(tableName);
  if (!table) {
    return `
      <div class="table-slot table-slot-empty">
        <strong>${escapeHtml(tableName)}</strong>
        <span>Not configured</span>
      </div>
    `;
  }
  return renderTableButton(table, table.id === state.selectedTableId);
}

function getTableByName(tableName) {
  return (
    state.tables.find((table) => normalizeTableName(table.name) === tableName) ||
    state.tables.find((table) => legacyTableNameToLabel(table.name) === tableName) ||
    null
  );
}

function getAvailableSeats(table) {
  return (table?.seats || []).filter((seat) => seat.status === "available");
}

function normalizeTableName(tableName) {
  return String(tableName || "").trim().toUpperCase();
}

function legacyTableNameToLabel(tableName) {
  const match = String(tableName || "").match(/(\d+)/);
  if (!match) {
    return null;
  }
  return TABLE_LABELS_BY_INDEX[Number(match[1])] || null;
}

function renderSeatPlanner(table) {
  const availableSeats = getAvailableSeats(table);
  const selectedLabel = state.selectedSeatNumbers.length
    ? formatSeatLabel(state.selectedSeatNumbers)
    : "";
  return `
    <div class="order-box" style="margin-top: 18px;">
      <div class="split-header">
        <div>
          <h3 class="section-title">Seat planner</h3>
          <p class="muted">Tap free seats to start a separate check for the same table.</p>
        </div>
        <span class="badge running">${table.seat_count} seats</span>
      </div>
      <div class="seat-grid" style="margin-top: 16px;">
        ${table.seats.map(renderSeatChip).join("")}
      </div>
      ${
        availableSeats.length
          ? `
            <div class="status-banner info" style="margin-top: 16px;">
              ${
                state.selectedSeatNumbers.length
                  ? `${escapeHtml(selectedLabel)} selected for a new check.`
                  : "Select one or more free seats to start a new check."
              }
            </div>
            <div class="action-row" style="margin-top: 16px;">
              <button class="primary-btn" type="button" id="start-check-btn" data-table-id="${table.id}" ${state.selectedSeatNumbers.length ? "" : "disabled"}>
                ${state.selectedSeatNumbers.length ? `Start ${escapeHtml(selectedLabel)}` : "Start selected check"}
              </button>
            </div>
          `
          : `<div class="footer-note">All seats in this table cycle are already attached to a live, billing, or closed check.</div>`
      }
    </div>
  `;
}

function renderSeatChip(seat) {
  const selected = state.selectedSeatNumbers.includes(seat.seat_number);
  const clickable = seat.status === "available";
  return `
    <button
      class="seat-chip ${clickable ? "available" : "occupied"} ${selected ? "selected" : ""}"
      type="button"
      data-seat-number="${seat.seat_number}"
      ${clickable ? "" : "disabled"}
    >
      <strong>Seat ${seat.seat_number}</strong>
      <span>${escapeHtml(clickable ? "Free" : seat.seat_label || "Reserved")}</span>
    </button>
  `;
}

function renderWaiterCheckCard(order) {
  const activeLines = order.items.filter((item) => item.item_status === "active").length;
  return `
    <div class="order-box" style="margin-top: 18px;">
      <div class="split-header">
        <div>
          <div class="badge-row">
            <span class="badge running">${escapeHtml(order.seat_label)}</span>
            <span class="badge ${order.status}">${capitalize(order.status)}</span>
            <span class="badge empty">Check ${order.id}</span>
          </div>
          <h3 class="section-title" style="margin-top: 12px;">${escapeHtml(order.seat_label)}</h3>
          <div class="meta-stack">
            <span>Opened: ${formatDateTime(order.opened_at)}</span>
            <span>${activeLines} active lines</span>
          </div>
        </div>
      </div>
      ${
        order.status === "running"
          ? `
            <form class="form-grid js-add-item-form" data-order-id="${order.id}" style="margin-top: 18px;">
              <div class="field-grid span-6">
                <label class="label">Item</label>
                <input class="input" name="item_name" placeholder="e.g. Butter naan" required />
              </div>
              <div class="field-grid span-3">
                <label class="label">Qty</label>
                <input class="input" name="quantity" type="number" min="1" max="99" value="1" required />
              </div>
              <div class="field-grid span-12">
                <label class="label">Note</label>
                <input class="input" name="note" placeholder="less spicy, no ice, extra crispy..." />
              </div>
              <div class="span-12">
                <button class="primary-btn" type="submit">Send to kitchen</button>
              </div>
            </form>
          `
          : `<div class="status-banner alert" style="margin-top: 18px;">This check is already in billing or closed.</div>`
      }
      <div class="item-list" style="margin-top: 18px;">
        ${order.items.length ? order.items.map((item) => renderWaiterItemCard(order, item)).join("") : `<div class="empty-box"><p class="muted">No items added yet.</p></div>`}
      </div>
      ${
        order.status === "running"
          ? `
            <div class="action-row" style="margin-top: 16px;">
              <button class="secondary-btn js-send-bill-btn" type="button" data-order-id="${order.id}">Send bill to reception</button>
            </div>
          `
          : ""
      }
    </div>
  `;
}

function renderWaiterItemCard(order, item) {
  const readOnly = item.item_status === "cancelled" || order.status !== "running";
  return `
    <div class="item-card ${item.item_status === "cancelled" ? "cancelled" : ""} ${flashClass(item.id)}" data-item-id="${item.id}">
      <div class="badge-row">
        <span class="badge ${item.item_status === "active" ? item.kitchen_status : "cancelled"}">${escapeHtml(item.item_status === "active" ? item.kitchen_status : item.item_status)}</span>
        <span class="badge running">Qty ${item.quantity}</span>
      </div>
      <div class="form-grid" style="margin-top: 14px;">
        <div class="field-grid span-6">
          <label class="label">Item</label>
          <input class="input js-item-name" value="${escapeAttribute(item.item_name)}" ${readOnly ? "disabled" : ""} />
        </div>
        <div class="field-grid span-3">
          <label class="label">Qty</label>
          <input class="input js-item-quantity" type="number" min="1" max="99" value="${item.quantity}" ${readOnly ? "disabled" : ""} />
        </div>
        <div class="field-grid span-12">
          <label class="label">Note</label>
          <input class="input js-item-note" value="${escapeAttribute(item.note || "")}" placeholder="Optional note" ${readOnly ? "disabled" : ""} />
        </div>
      </div>
      <div class="item-actions" style="margin-top: 14px;">
        ${
          readOnly
            ? `<span class="muted">${item.item_status === "cancelled" ? "Cancelled item kept for history and billing review." : "Locked while billing is in progress."}</span>`
            : `
              <button class="secondary-btn js-save-item" data-order-id="${order.id}" data-item-id="${item.id}">Save changes</button>
              <button class="ghost-btn js-cancel-item" data-order-id="${order.id}" data-item-id="${item.id}">Cancel item</button>
            `
        }
      </div>
    </div>
  `;
}

function renderKitchenItemCard(order, item) {
  const displayStatus = kitchenDisplayStatus(item);
  return `
    <div class="item-card kitchen-item-card ${item.item_status === "cancelled" ? "cancelled" : ""} ${flashClass(item.id)}">
      <div class="badge-row">
        <span class="badge ${item.item_status === "active" ? displayStatus : "cancelled"}">${escapeHtml(item.item_status === "active" ? displayStatus : item.item_status)}</span>
        <span class="badge running">Qty ${item.quantity}</span>
      </div>
      <h4 style="margin-top: 10px;">${escapeHtml(item.item_name)}</h4>
      <div class="meta-stack kitchen-item-meta">
        <span>${escapeHtml(order.seat_label)} · Check ${order.id}</span>
        <span>${item.note ? escapeHtml(item.note) : "No special note"}</span>
      </div>
      ${
        item.item_status === "active"
          ? `
          <div class="compact-actions kitchen-actions" style="margin-top: 12px;">
            ${["new", "ready"]
              .map(
                (statusLabel) => `
                  <button
                    class="status-btn ${statusLabel === displayStatus ? "secondary-btn" : "ghost-btn"}"
                    data-kitchen-order-id="${order.id}"
                    data-kitchen-item-id="${item.id}"
                    data-kitchen-status="${statusLabel}"
                  >
                    ${capitalize(statusLabel)}
                  </button>
                `,
              )
              .join("")}
          </div>
        `
          : `<div class="footer-note">This item was cancelled by the waiter. Keep it visible for context.</div>`
      }
    </div>
  `;
}

function kitchenDisplayStatus(item) {
  if (item.item_status !== "active") {
    return "cancelled";
  }
  return item.kitchen_status === "ready" ? "ready" : "new";
}

function renderBillingRow(item, index) {
  return `
    <tr data-billing-index="${index}">
      <td>
        <strong>${escapeHtml(item.item_name)}</strong>
        <span class="table-note">${escapeHtml(item.source_status)}</span>
        ${item.note ? `<span class="table-note">${escapeHtml(item.note)}</span>` : ""}
        <input type="hidden" class="js-order-item-id" value="${item.order_item_id ?? ""}" />
        <input type="hidden" class="js-source-status" value="${escapeAttribute(item.source_status)}" />
      </td>
      <td>${item.consumed_quantity}</td>
      <td><input class="input js-billed-quantity" type="number" min="0" max="99" value="${item.billed_quantity}" /></td>
      <td><input class="input js-unit-price" type="number" min="0" step="0.01" value="${formatNumber(item.unit_price)}" /></td>
      <td><input class="checkbox js-include" type="checkbox" ${item.include_in_bill ? "checked" : ""} /></td>
      <td class="js-line-total">${moneyLabel(item.line_total)}</td>
    </tr>
  `;
}

function renderHistoryRow(entry) {
  return `
    <div class="history-row">
      <h4>${escapeHtml(entry.description)}</h4>
      <div class="meta-stack">
        <span>${escapeHtml(entry.actor_name)} · ${capitalize(entry.actor_role)}</span>
        <span>${formatDateTime(entry.created_at)}</span>
      </div>
    </div>
  `;
}

function renderWaiterEmptyState(table) {
  return `
    <div class="empty-box" style="margin-top: 18px;">
      <h3 class="section-title">Table is available</h3>
      <p class="muted">
        ${
          table.pending_bills_count
            ? "This table is free for new guests. Older bills from earlier service are still waiting at reception."
            : "Open the table first, then choose the seats that belong to each payment group."
        }
      </p>
      <button class="primary-btn" id="open-table-btn" data-table-id="${table.id}">Open table</button>
    </div>
  `;
}

function renderPendingBillCard(order) {
  const selected = order.order_id === state.selectedReceptionOrderId;
  const table = state.tables.find((entry) => entry.id === order.table_id);
  const liveOrderText = table?.active_orders_count
    ? `${table.active_orders_count} live checks are active now.`
    : table?.status === "empty"
      ? "Table is free for next guests."
      : "Waiter still needs to release this table.";
  return `
    <button
      class="pending-bill-card ${selected ? "active" : ""}"
      data-pending-order-id="${order.order_id}"
      data-pending-table-id="${order.table_id}"
    >
      <div class="badge-row">
        <span class="badge billing">${escapeHtml(order.table_name)}</span>
        <span class="badge running">${escapeHtml(order.seat_label)}</span>
      </div>
      <h4>${moneyLabel(order.subtotal)}</h4>
      <div class="meta-stack">
        <span>Check ${order.order_id}</span>
        <span>${order.items_count} total qty</span>
        <span>Updated ${formatDateTime(order.updated_at)}</span>
        <span>${escapeHtml(liveOrderText)}</span>
      </div>
    </button>
  `;
}

function renderReceptionLiveCheckCard(order) {
  return `
    <div class="history-row">
      <div class="badge-row">
        <span class="badge running">${escapeHtml(order.seat_label)}</span>
        <span class="badge empty">Check ${order.id}</span>
      </div>
      <div class="meta-stack" style="margin-top: 10px;">
        <span>Opened: ${formatDateTime(order.opened_at)}</span>
        <span>Live items: ${order.items.filter((item) => item.item_status === "active").reduce((sum, item) => sum + item.quantity, 0)}</span>
      </div>
    </div>
  `;
}

function renderBadge(status) {
  return `<span class="badge ${escapeHtml(status)}">${escapeHtml(displayStatus(status))}</span>`;
}

function bindCommonEvents() {
  document.querySelector("#logout-btn")?.addEventListener("click", logout);
  document.querySelector("#refresh-view")?.addEventListener("click", () => {
    void refreshRoleData();
  });
  document.querySelectorAll(".table-button[data-table-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedTableId = Number(button.dataset.tableId);
      if (state.user?.role === "receptionist") {
        state.selectedReceptionOrderId = getPreferredPendingBillForTable(state.selectedTableId)?.order_id || null;
      }
      await loadSelectedTable();
      render();
      scrollToTableDetails();
    });
  });
}

function bindLoginEvents() {
  document.querySelector("#login-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const username = String(formData.get("username") || "").trim();
    const password = String(formData.get("password") || "");
    if (!username || !password) {
      state.error = "Username and password are required.";
      render();
      return;
    }
    await login(username, password);
  });

  document.querySelectorAll(".demo-fill-btn").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector("#username").value = button.dataset.username;
      document.querySelector("#password").value = button.dataset.password;
    });
  });
}

function bindWaiterEvents() {
  document.querySelector("#open-table-btn")?.addEventListener("click", async (event) => {
    const tableId = Number(event.currentTarget.dataset.tableId);
    await execute("Opening table", async () => {
      await api(`/tables/${tableId}/open`, { method: "POST" });
      state.selectedTableId = tableId;
      state.selectedSeatNumbers = [];
      await refreshRoleData();
    });
  });

  document.querySelectorAll("[data-seat-number]").forEach((button) => {
    button.addEventListener("click", () => {
      const seatNumber = Number(button.dataset.seatNumber);
      if (state.selectedSeatNumbers.includes(seatNumber)) {
        state.selectedSeatNumbers = state.selectedSeatNumbers.filter((value) => value !== seatNumber);
      } else {
        state.selectedSeatNumbers = [...state.selectedSeatNumbers, seatNumber].sort((left, right) => left - right);
      }
      render();
    });
  });

  document.querySelector("#start-check-btn")?.addEventListener("click", async (event) => {
    const tableId = Number(event.currentTarget.dataset.tableId);
    const seatNumbers = [...state.selectedSeatNumbers];
    await execute("Starting seat check", async () => {
      await api(`/tables/${tableId}/checks`, {
        method: "POST",
        body: { seat_numbers: seatNumbers },
      });
      state.notice = `${formatSeatLabel(seatNumbers)} started.`;
      state.selectedSeatNumbers = [];
      await refreshRoleData();
    });
  });

  document.querySelector("#mark-empty-btn")?.addEventListener("click", async (event) => {
    const tableId = Number(event.currentTarget.dataset.tableId);
    await execute("Marking table empty", async () => {
      await api(`/tables/${tableId}/mark-empty`, { method: "POST" });
      state.selectedTableId = tableId;
      state.selectedSeatNumbers = [];
      await refreshRoleData();
    });
  });

  document.querySelectorAll(".js-send-bill-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      const orderId = Number(button.dataset.orderId);
      await execute("Sending bill to reception", async () => {
        await api(`/orders/${orderId}/status`, {
          method: "PATCH",
          body: { status: "billing" },
        });
        state.notice = "Bill sent to reception.";
        await refreshRoleData();
      });
    });
  });

  document.querySelectorAll(".js-add-item-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(form);
      const orderId = Number(form.dataset.orderId);
      await execute("Sending item to kitchen", async () => {
        await api(`/orders/${orderId}/items`, {
          method: "POST",
          body: {
            item_name: String(formData.get("item_name") || ""),
            quantity: Number(formData.get("quantity") || 1),
            note: String(formData.get("note") || "").trim() || null,
          },
        });
        await refreshRoleData();
      });
    });
  });

  document.querySelectorAll(".js-save-item").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest(".item-card[data-item-id]");
      const orderId = Number(button.dataset.orderId);
      const itemId = Number(button.dataset.itemId);
      const itemNameInput = card?.querySelector(".js-item-name");
      const quantityInput = card?.querySelector(".js-item-quantity");
      const noteInput = card?.querySelector(".js-item-note");

      if (!itemNameInput || !quantityInput || !noteInput) {
        state.error = "Could not read the item fields. Please reopen the table and try again.";
        render();
        return;
      }

      const payload = {
        item_name: itemNameInput.value.trim(),
        quantity: Number(quantityInput.value || 1),
        note: noteInput.value.trim() || null,
      };

      if (!payload.item_name) {
        state.error = "Item name cannot be empty.";
        render();
        return;
      }

      await execute("Saving item changes", async () => {
        await api(`/orders/${orderId}/items/${itemId}`, {
          method: "PATCH",
          body: payload,
        });
        state.notice = "Item changes saved.";
        await refreshRoleData();
      });
    });
  });

  document.querySelectorAll(".js-cancel-item").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("Cancel this item? It will remain visible in history.")) {
        return;
      }
      const orderId = Number(button.dataset.orderId);
      const itemId = Number(button.dataset.itemId);
      await execute("Cancelling item", async () => {
        await api(`/orders/${orderId}/items/${itemId}/cancel`, { method: "POST" });
        await refreshRoleData();
      });
    });
  });
}

function bindKitchenEvents() {
  document.querySelectorAll("[data-kitchen-status]").forEach((button) => {
    button.addEventListener("click", async () => {
      await execute("Updating kitchen status", async () => {
        await api(`/kitchen/orders/${button.dataset.kitchenOrderId}/items/${button.dataset.kitchenItemId}/status`, {
          method: "PATCH",
          body: { kitchen_status: button.dataset.kitchenStatus },
        });
        await refreshRoleData();
      });
    });
  });
}

function bindReceptionEvents() {
  document.querySelectorAll("[data-pending-order-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedTableId = Number(button.dataset.pendingTableId);
      state.selectedReceptionOrderId = Number(button.dataset.pendingOrderId);
      await loadSelectedTable();
      render();
      scrollToTableDetails();
    });
  });

  document.querySelectorAll(".js-billed-quantity, .js-unit-price, .js-include, #discount").forEach((element) => {
    element.addEventListener("input", updateBillingTotals);
    element.addEventListener("change", updateBillingTotals);
  });

  document.querySelector("#save-billing-btn")?.addEventListener("click", async (event) => {
    const orderId = Number(event.currentTarget.dataset.orderId);
    await execute("Saving billing draft", async () => {
      const payload = collectBillingForm();
      state.billing = await api(`/reception/orders/${orderId}/billing`, {
        method: "PUT",
        body: payload,
      });
      await refreshRoleData();
    });
  });

  document.querySelector("#checkout-btn")?.addEventListener("click", async (event) => {
    const orderId = Number(event.currentTarget.dataset.orderId);
    await execute("Completing payment", async () => {
      const payload = collectBillingForm();
      await api(`/reception/orders/${orderId}/billing`, {
        method: "PUT",
        body: payload,
      });
      await api(`/reception/orders/${orderId}/checkout`, {
        method: "POST",
        body: {
          discount: payload.discount,
          payment_method: document.querySelector("#payment_method").value,
          notes: document.querySelector("#payment_notes").value.trim() || null,
        },
      });
      state.selectedReceptionOrderId = null;
      state.notice = "Payment recorded. The bill is closed.";
      await refreshRoleData();
    });
  });

  updateBillingTotals();
}

async function login(username, password) {
  state.error = "";
  state.notice = "";
  state.busy = "Signing in";
  render();
  try {
    const response = await api("/auth/login", {
      method: "POST",
      body: { username, password },
      authenticated: false,
    });
    state.token = response.access_token;
    state.user = response.user;
    persistSession();
    connectSocket();
    await refreshRoleData();
  } catch (error) {
    state.error = error.message;
  } finally {
    state.busy = "";
    render();
  }
}

function logout() {
  if (state.socket) {
    state.socket.close();
  }
  clearSession();
  state.tables = [];
  state.kitchenTables = [];
  state.selectedTable = null;
  state.selectedTableId = null;
  state.selectedSeatNumbers = [];
  state.pendingBills = [];
  state.selectedReceptionOrder = null;
  state.selectedReceptionOrderId = null;
  state.billing = null;
  state.notice = "";
  state.error = "";
  state.busy = "";
  render();
}

async function refreshRoleData() {
  state.error = "";
  if (!state.user) {
    return;
  }

  if (state.user.role === "kitchen") {
    state.kitchenTables = await api("/kitchen/active");
    render();
    return;
  }

  if (state.user.role === "receptionist") {
    const [tables, pendingBills] = await Promise.all([
      api("/tables"),
      api("/reception/orders/pending"),
    ]);
    state.tables = tables;
    state.pendingBills = pendingBills;
  } else {
    state.tables = await api("/tables");
    state.pendingBills = [];
    state.selectedReceptionOrder = null;
    state.selectedReceptionOrderId = null;
  }

  if (!state.tables.length) {
    state.selectedTable = null;
    state.selectedTableId = null;
    state.selectedSeatNumbers = [];
    state.pendingBills = [];
    state.selectedReceptionOrder = null;
    state.selectedReceptionOrderId = null;
    state.billing = null;
    render();
    return;
  }

  if (!state.selectedTableId || !state.tables.some((table) => table.id === state.selectedTableId)) {
    state.selectedTableId = state.tables[0].id;
  }
  await loadSelectedTable();
  render();
}

async function loadSelectedTable() {
  if (!state.selectedTableId) {
    state.selectedTable = null;
    state.selectedSeatNumbers = [];
    state.selectedReceptionOrder = null;
    state.selectedReceptionOrderId = null;
    state.billing = null;
    return;
  }
  state.selectedTable = await api(`/tables/${state.selectedTableId}`);
  const availableSeatNumbers = new Set(getAvailableSeats(state.selectedTable).map((seat) => seat.seat_number));
  state.selectedSeatNumbers = state.selectedSeatNumbers.filter((seatNumber) => availableSeatNumbers.has(seatNumber));
  if (state.user?.role === "receptionist") {
    syncSelectedReceptionOrder();
    if (state.selectedReceptionOrderId) {
      await loadReceptionOrder(state.selectedReceptionOrderId);
    } else {
      state.selectedReceptionOrder = null;
      state.billing = null;
    }
  } else {
    state.selectedReceptionOrder = null;
    state.selectedReceptionOrderId = null;
    state.billing = null;
  }
}

async function loadReceptionOrder(orderId) {
  const [order, billing] = await Promise.all([
    api(`/orders/${orderId}`),
    api(`/reception/orders/${orderId}/billing`),
  ]);
  state.selectedReceptionOrder = order;
  state.billing = billing;
}

function syncSelectedReceptionOrder() {
  if (!state.selectedTable) {
    state.selectedReceptionOrderId = null;
    return;
  }

  const pendingForTable = getPendingBillsForTable(state.selectedTable.id);
  const stillValid = pendingForTable.some((order) => order.order_id === state.selectedReceptionOrderId);
  if (stillValid) {
    return;
  }
  state.selectedReceptionOrderId = pendingForTable[0]?.order_id || null;
}

function getPendingBillsForTable(tableId) {
  return state.pendingBills.filter((bill) => bill.table_id === tableId);
}

function getPreferredPendingBillForTable(tableId) {
  return getPendingBillsForTable(tableId)[0] || null;
}

function collectBillingForm() {
  const rows = Array.from(document.querySelectorAll("[data-billing-index]"));
  const items = rows.map((row) => ({
    order_item_id: row.querySelector(".js-order-item-id").value ? Number(row.querySelector(".js-order-item-id").value) : null,
    item_name: row.querySelector("strong").textContent.trim(),
    note: row.querySelectorAll(".table-note")[1]?.textContent?.trim() || null,
    source_status: row.querySelector(".js-source-status").value,
    consumed_quantity: Number(row.children[1].textContent.trim() || 0),
    billed_quantity: Number(row.querySelector(".js-billed-quantity").value || 0),
    unit_price: Number(row.querySelector(".js-unit-price").value || 0),
    include_in_bill: row.querySelector(".js-include").checked,
  }));

  return {
    items,
    discount: Number(document.querySelector("#discount")?.value || 0),
  };
}

function updateBillingTotals() {
  if (!document.querySelector("[data-billing-index]")) {
    return;
  }

  const rows = Array.from(document.querySelectorAll("[data-billing-index]"));
  let subtotal = 0;
  rows.forEach((row) => {
    const qty = Number(row.querySelector(".js-billed-quantity").value || 0);
    const price = Number(row.querySelector(".js-unit-price").value || 0);
    const include = row.querySelector(".js-include").checked;
    const lineTotal = include ? qty * price : 0;
    row.querySelector(".js-line-total").textContent = moneyLabel(lineTotal);
    subtotal += lineTotal;
  });

  const discount = Number(document.querySelector("#discount").value || 0);
  const finalTotal = Math.max(subtotal - discount, 0);
  document.querySelector("#subtotal-value").textContent = moneyLabel(subtotal);
  document.querySelector("#discount-value").textContent = moneyLabel(discount);
  document.querySelector("#final-total-value").textContent = moneyLabel(finalTotal);
}

async function execute(label, work) {
  state.error = "";
  state.notice = "";
  state.busy = label;
  render();
  try {
    await work();
  } catch (error) {
    state.error = error.message;
  } finally {
    state.busy = "";
    render();
  }
}

function connectSocket() {
  if (!state.token) {
    return;
  }

  if (state.socket) {
    state.socket.close();
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  state.socket = new WebSocket(`${protocol}://${window.location.host}/ws?token=${encodeURIComponent(state.token)}`);

  state.socket.onmessage = async (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "connected") {
      state.notice = `Live updates connected for ${capitalize(message.payload.role)}.`;
      render();
      return;
    }

    if (message.payload?.item_id) {
      state.flashes[message.payload.item_id] = message.type;
      window.setTimeout(() => {
        delete state.flashes[message.payload.item_id];
        render();
      }, 2200);
    }

    state.notice = humanizeEvent(message.type, message.payload);
    await refreshRoleData();
  };

  state.socket.onclose = () => {
    if (!state.user) {
      return;
    }
    state.notice = "Realtime link dropped. Reconnecting...";
    render();
    window.setTimeout(() => {
      if (state.user) {
        connectSocket();
      }
    }, 1500);
  };
}

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.authenticated === false ? {} : { Authorization: `Bearer ${state.token}` }),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    let message = "Request failed";
    try {
      const errorData = await response.json();
      message = errorData.detail || message;
    } catch {
      message = `${response.status} ${response.statusText}`;
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function humanizeEvent(type, payload) {
  const names = {
    table_updated: "Table opened for service.",
    check_created: "New seat check started.",
    table_emptied: "Waiter marked the table empty.",
    item_added: "New item sent live to kitchen.",
    item_updated: "Order item updated.",
    item_cancelled: "An item was cancelled but kept in history.",
    kitchen_status_changed: "Kitchen status changed.",
    order_status_changed: payload?.order_status === "billing" ? "Waiter sent a seat check to reception." : "Order returned to running service.",
    billing_saved: "Billing draft saved.",
    payment_completed: "Payment completed.",
  };
  if (payload?.table_id) {
    const tableName = state.tables.find((table) => table.id === payload.table_id)?.name || `Table ${payload.table_id}`;
    return `${names[type] || "Live update received."} ${tableName}.`;
  }
  return names[type] || "Live update received.";
}

function displayStatus(status) {
  const labels = {
    billing: "running",
    closed: "running",
  };
  return labels[status] || status;
}

function renderReceptionTableNotice(table) {
  if (table.pending_bills_count) {
    return "This table has pending seat checks waiting at reception. Keep working from the billing queue below. The waiter still decides when the whole table becomes empty.";
  }
  if (table.status === "empty") {
    return "No current service on this table right now.";
  }
  return "Waiter is still serving this table. Each seat check will appear here separately after the waiter sends it.";
}

function persistSession() {
  localStorage.setItem(STORAGE_TOKEN, state.token);
  localStorage.setItem(STORAGE_USER, JSON.stringify(state.user));
}

function clearSession() {
  localStorage.removeItem(STORAGE_TOKEN);
  localStorage.removeItem(STORAGE_USER);
  state.token = "";
  state.user = null;
}

function scrollToTableDetails() {
  const detailPanel = document.querySelector("#table-detail-panel");
  if (!detailPanel) {
    return;
  }
  if (window.innerWidth > 1100) {
    return;
  }
  window.setTimeout(() => {
    detailPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 60);
}

function flashClass(itemId) {
  const kind = state.flashes[itemId];
  return kind ? `flash-${kind}` : "";
}

function formatDateTime(value) {
  if (!value) {
    return "Just now";
  }
  return new Date(value).toLocaleString([], {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function capitalize(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatSeatLabel(seatNumbers) {
  const normalized = [...new Set((seatNumbers || []).map((value) => Number(value)))].sort((left, right) => left - right);
  if (!normalized.length) {
    return "No seats";
  }
  if (normalized.length === 1) {
    return `Seat ${normalized[0]}`;
  }
  return `Seats ${normalized.join(" + ")}`;
}

function moneyLabel(value) {
  return `Rs ${Number(value || 0).toFixed(2)}`;
}

function formatNumber(value) {
  return Number(value || 0).toFixed(2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#96;");
}

function readJson(value) {
  if (!value) {
    return null;
  }
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
