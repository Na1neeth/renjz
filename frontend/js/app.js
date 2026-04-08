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
  receptionSalesToday: null,
  receptionSalesWeek: null,
  salesMonth: null,
  salesSelectedMonth: null,
  kitchenTables: [],
  menuItems: [],
  socket: null,
  notice: "",
  error: "",
  busy: "",
  flashes: {},
};

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
  if (state.user.role === "sales") {
    bindSalesEvents();
  }
}

function renderLogin() {
  return `
    <div class="login-shell">
      <section class="login-card login-card-simple">
        <div class="login-brand">
          <div class="eyebrow">Staff Login</div>
          <h1 class="hero-title">Renjz Kitchen</h1>
        </div>
        ${state.error ? `<div class="error-strip">${escapeHtml(state.error)}</div>` : ""}
        <form id="login-form" class="login-form">
          <div class="field-grid">
            <label class="label" for="username">Username</label>
            <input id="username" class="input" name="username" autocomplete="username" required autofocus />
          </div>
          <div class="field-grid">
            <label class="label" for="password">Password</label>
            <input id="password" class="input" name="password" type="password" autocomplete="current-password" required />
          </div>
          <div class="action-row">
            <button class="primary-btn" type="submit">${state.busy || "Sign in"}</button>
          </div>
        </form>
      </section>
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
              <button class="ghost-btn" type="button" id="refresh-view">Refresh</button>
              <button class="secondary-btn" type="button" id="logout-btn">Log out</button>
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
  if (state.user.role === "sales") {
    return renderSalesView();
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
  const kitchenTables = [...state.kitchenTables].sort(
    (left, right) => compareDateAsc(left.last_activity_at, right.last_activity_at) || left.id - right.id,
  );
  return `
    <main class="view-grid">
      <section class="panel">
        <h2 class="panel-title">Kitchen dashboard</h2>
        <p class="muted">Simple kitchen queue for phone use. Only new and ready are used here.</p>
      </section>
      <section class="panel">
        <div class="split-header">
          <div>
            <h2 class="panel-title">Today's menu</h2>
            <p class="muted">Kitchen controls what waiters can send. Add or remove items here whenever the menu changes.</p>
          </div>
          <span class="badge running">${state.menuItems.length} items</span>
        </div>
        <form id="menu-item-form" class="form-grid" style="margin-top: 18px;">
          <div class="field-grid span-9">
            <label class="label" for="menu-item-name">Menu item</label>
            <input id="menu-item-name" class="input" name="name" placeholder="e.g. Ghee roast" required />
          </div>
          <div class="field-grid span-3">
            <label class="label">&nbsp;</label>
            <button class="primary-btn" type="submit">Add item</button>
          </div>
        </form>
        <div class="item-list" style="margin-top: 16px;">
          ${
            state.menuItems.length
              ? state.menuItems.map((item) => renderKitchenMenuCard(item)).join("")
              : `<div class="empty-box"><p class="muted">No menu items yet. Add today's dishes here so waiters can select them.</p></div>`
          }
        </div>
      </section>
      <section class="kitchen-grid">
        ${
          kitchenTables.length
            ? kitchenTables
                .map((table) => {
                  const entries = table.active_orders
                    .flatMap((order) => order.items.map((item) => ({ order, item })))
                    .sort(
                      (left, right) =>
                        compareDateAsc(
                          left.item.updated_at || left.item.created_at,
                          right.item.updated_at || right.item.created_at,
                        ) ||
                        compareDateAsc(
                          left.order.updated_at || left.order.opened_at,
                          right.order.updated_at || right.order.opened_at,
                        ) ||
                        left.item.id - right.item.id,
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
                        <span class="badge running kitchen-table-name">${escapeHtml(table.name)}</span>
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
                pendingBillsForTable.length
                  ? `
                    <div class="split-header" style="margin-top: 18px;">
                      <div>
                        <h3 class="section-title">Pending bills for ${escapeHtml(table.name)}</h3>
                        <p class="muted">Reception only works on the selected table. Choose the seat check you want to bill.</p>
                      </div>
                      <span class="badge billing">${pendingBillsForTable.length} pending</span>
                    </div>
                    <div class="pending-bills-list" style="margin-top: 16px;">
                      ${pendingBillsForTable.map(renderPendingBillCard).join("")}
                    </div>
                  `
                  : `
                    <div class="status-banner info" style="margin-top: 16px;">
                      ${renderReceptionTableNotice(table)}
                    </div>
                  `
              }
              ${
                runningOrders.length
                  ? `
                    <div class="split-header" style="margin-top: 18px;">
                      <div>
                        <h3 class="section-title">Live checks</h3>
                        <p class="muted">These checks are still active with the waiter.</p>
                      </div>
                      <span class="badge running">${runningOrders.length} live</span>
                    </div>
                    <div class="item-list" style="margin-top: 16px;">
                      ${runningOrders.map(renderReceptionLiveCheckCard).join("")}
                    </div>
                  `
                  : ""
              }
            </section>
          `
            : ""
        }
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
                  <button class="primary-btn" type="button" id="print-bill-btn" data-order-id="${billingOrder.id}">Print bill</button>
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
              <h3 class="section-title">Select a table bill</h3>
              <p class="muted">
                ${
                  !table
                    ? "Choose a table first."
                    : pendingBillsForTable.length
                      ? "Choose one pending bill from the selected table to price items, apply discounts, and complete payment."
                      : "This table has no pending bills right now."
                }
              </p>
            </section>
          `
        }
      </section>
    </main>
  `;
}

function renderSalesView() {
  const today = state.receptionSalesToday;
  const week = state.receptionSalesWeek;
  const month = state.salesMonth;
  if (!today || !week || !month) {
    return `
      <main class="view-grid">
        <section class="panel">
          <h2 class="panel-title">Sales dashboard</h2>
          <p class="muted">Loading payment totals, trends, and item sales.</p>
        </section>
      </main>
    `;
  }

  const selectedMonth = state.salesSelectedMonth || formatMonthValue(month.end_date);
  const [selectedYear, selectedMonthNumber] = parseMonthValue(selectedMonth);
  const availableYears = getSalesYearOptions();
  const availableMonths = getSalesMonthOptionsForYear(selectedYear);
  const monthItemQty = month.items.reduce((sum, item) => sum + item.quantity_sold, 0);
  return `
    <main class="view-grid">
      <section class="panel">
        <div class="split-header">
          <div>
            <h2 class="panel-title">Sales dashboard</h2>
            <p class="muted">Dedicated reporting view based on completed payments in ${escapeHtml(today.timezone)}.</p>
          </div>
          <span class="badge ready">${month.closed_bills_count} closed bills in ${escapeHtml(formatMonthHeading(selectedMonth))}</span>
        </div>
        <div class="sales-summary-grid" style="margin-top: 16px;">
          ${renderSalesMetricCard("Today revenue", moneyLabel(today.net_sales), `${today.closed_bills_count} bills closed today`)}
          ${renderSalesMetricCard("Today gross", moneyLabel(today.gross_sales), `Discounts ${moneyLabel(today.discount_total)}`)}
          ${renderSalesMetricCard("7 day revenue", moneyLabel(week.net_sales), `${week.closed_bills_count} bills in 7 days`)}
          ${renderSalesMetricCard(`${formatMonthHeading(selectedMonth)} revenue`, moneyLabel(month.net_sales), `${month.closed_bills_count} bills in selected month`)}
          ${renderSalesMetricCard(`${formatMonthHeading(selectedMonth)} items`, String(monthItemQty), `${month.items.length} distinct billed items`)}
        </div>
      </section>
      <section class="panel sales-trend-panel">
          <div class="split-header">
            <div>
              <h3 class="section-title">Revenue trend</h3>
              <p class="muted">Daily net collections for ${escapeHtml(formatMonthHeading(selectedMonth))}.</p>
            </div>
            <div class="sales-filter-row">
              <div class="field-grid">
                <label class="label" for="sales-year">Year</label>
                <select class="select" id="sales-year" name="sales-year">
                  ${availableYears.map((year) => `<option value="${year}" ${year === selectedYear ? "selected" : ""}>${year}</option>`).join("")}
                </select>
              </div>
              <div class="field-grid">
                <label class="label" for="sales-month">Month</label>
                <select class="select" id="sales-month" name="sales-month">
                  ${availableMonths
                    .map((monthOption) => `<option value="${monthOption.month}" ${monthOption.month === selectedMonthNumber ? "selected" : ""}>${escapeHtml(monthOption.label)}</option>`)
                    .join("")}
                </select>
              </div>
            </div>
          </div>
          ${renderSalesTrendChart(month)}
      </section>
      <section class="panel sales-breakdown-panel">
        <div class="split-header">
          <div>
            <h3 class="section-title">Daily breakdown</h3>
            <p class="muted">Best view of the selected month.</p>
          </div>
        </div>
          <div class="history-list sales-breakdown-list" style="margin-top: 12px;">
            ${
              month.daily_totals.length
                ? [...month.daily_totals].reverse().map(renderSalesDayRow).join("")
                : `<div class="empty-box"><p class="muted">No payments recorded yet.</p></div>`
            }
          </div>
        </section>
    </main>
  `;
}

function renderSalesMetricCard(label, value, note) {
  return `
    <div class="sales-metric-card">
      <span class="label">${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <span class="muted">${escapeHtml(note)}</span>
    </div>
  `;
}

function renderSalesTrendChart(report) {
  const days = [...report.daily_totals].reverse();
  const maxNetSales = Math.max(...days.map((day) => Number(day.net_sales || 0)), 1);
  return `
    <div class="sales-chart" style="margin-top: 16px; grid-template-columns: repeat(${days.length}, minmax(0, 1fr));">
      ${days
        .map((day) => {
          const netSales = Number(day.net_sales || 0);
          const height = Math.max(10, Math.round((netSales / maxNetSales) * 160));
          const displayValue = netSales > 0 ? moneyLabel(day.net_sales) : "";
          return `
            <div class="sales-chart-column" title="${escapeHtml(formatDateLabel(day.date))} · ${escapeHtml(moneyLabel(day.net_sales))}">
              <span class="sales-chart-value">${escapeHtml(displayValue)}</span>
              <div class="sales-chart-bar-shell">
                <div class="sales-chart-bar" style="height: ${height}px;"></div>
              </div>
              <span class="sales-chart-label">${escapeHtml(formatMiniDateLabel(day.date))}</span>
            </div>
          `;
        })
        .join("")}
    </div>
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
  const hasMenuItems = state.menuItems.length > 0;
  return `
    <div class="order-box" data-order-card-id="${order.id}" style="margin-top: 18px;">
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
            ${
              hasMenuItems
                ? `
                  <div class="status-banner info" style="margin-top: 18px;">
                    Waiters can send only the items listed in today's kitchen menu.
                  </div>
                `
                : `
                  <div class="status-banner alert" style="margin-top: 18px;">
                    Today's menu is empty. Ask the kitchen to add items before sending orders.
                  </div>
                `
            }
            <form class="form-grid js-add-item-form" data-order-id="${order.id}" style="margin-top: 18px;">
              <div class="field-grid span-6">
                <label class="label">Item</label>
                <select class="select" name="item_name" ${hasMenuItems ? "required" : "disabled"}>
                  ${renderMenuOptions("", { includePlaceholder: true })}
                </select>
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
                <button class="primary-btn" type="submit" ${hasMenuItems ? "" : "disabled"}>Send to kitchen</button>
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
          <select class="select js-item-name" ${readOnly ? "disabled" : ""}>
            ${renderMenuOptions(item.item_name)}
          </select>
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

function renderMenuOptions(selectedName, options = {}) {
  const includePlaceholder = options.includePlaceholder === true;
  const hasSelectedMenuItem = state.menuItems.some((item) => item.name === selectedName);
  let html = includePlaceholder
    ? `<option value="" ${selectedName ? "" : "selected"} disabled>Select from today's menu</option>`
    : "";

  if (selectedName && !hasSelectedMenuItem) {
    html += `<option value="${escapeAttribute(selectedName)}" selected>${escapeHtml(selectedName)} (not in today's menu)</option>`;
  }

  html += state.menuItems
    .map(
      (item) => `
        <option value="${escapeAttribute(item.name)}" ${item.name === selectedName ? "selected" : ""}>${escapeHtml(item.name)}</option>
      `,
    )
    .join("");

  return html;
}

function renderKitchenMenuCard(item) {
  return `
    <div class="item-card menu-item-card">
      <div class="menu-item-row">
        <div>
          <h4>${escapeHtml(item.name)}</h4>
          <div class="meta-stack kitchen-item-meta">
            <span>Added ${formatDateTime(item.created_at)}</span>
            <span>Last updated ${formatDateTime(item.updated_at)}</span>
          </div>
        </div>
        <button class="ghost-btn js-delete-menu-item" type="button" data-menu-item-id="${item.id}" data-menu-item-name="${escapeAttribute(item.name)}">Delete</button>
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
        <input type="hidden" class="js-item-name" value="${escapeAttribute(item.item_name)}" />
        <input type="hidden" class="js-item-note" value="${escapeAttribute(item.note || "")}" />
      </td>
      <td class="js-consumed-quantity">${item.consumed_quantity}</td>
      <td><input class="input js-billed-quantity" name="billed_quantity" type="number" min="0" max="99" value="${item.billed_quantity}" /></td>
      <td><input class="input js-unit-price" name="unit_price" type="number" min="0" step="0.01" value="${formatNumber(item.unit_price)}" /></td>
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
  return `
    <button
      class="pending-bill-card ${selected ? "active" : ""}"
      type="button"
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
        <span>${escapeHtml(order.seat_label)} is waiting for payment.</span>
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

function renderSalesDayRow(day) {
  return `
    <div class="history-row sales-row">
      <div>
        <h4>${escapeHtml(formatDateLabel(day.date))}</h4>
        <div class="meta-stack">
          <span>${day.closed_bills_count} closed bills</span>
          <span>Gross ${moneyLabel(day.gross_sales)} · Discount ${moneyLabel(day.discount_total)}</span>
        </div>
      </div>
      <strong>${moneyLabel(day.net_sales)}</strong>
    </div>
  `;
}

function renderBadge(status) {
  return `<span class="badge ${escapeHtml(status)}">${escapeHtml(displayStatus(status))}</span>`;
}

function bindCommonEvents() {
  document.querySelector("#logout-btn")?.addEventListener("click", (event) => {
    event.preventDefault();
    void logout();
  });
  document.querySelector("#refresh-view")?.addEventListener("click", (event) => {
    event.preventDefault();
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
      }, { scrollAnchorSelector: `[data-order-card-id="${orderId}"]` });
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
      }, { scrollAnchorSelector: `[data-order-card-id="${orderId}"]` });
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
      }, { scrollAnchorSelector: `[data-order-card-id="${orderId}"]` });
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
      }, { scrollAnchorSelector: `[data-order-card-id="${orderId}"]` });
    });
  });
}

function bindKitchenEvents() {
  document.querySelector("#menu-item-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    await execute("Adding menu item", async () => {
      await api("/menu", {
        method: "POST",
        body: { name: String(formData.get("name") || "") },
      });
      state.notice = "Today's menu updated.";
      await refreshRoleData();
    });
  });

  document.querySelectorAll(".js-delete-menu-item").forEach((button) => {
    button.addEventListener("click", async () => {
      const itemName = button.dataset.menuItemName || "this item";
      if (!window.confirm(`Remove ${itemName} from today's menu?`)) {
        return;
      }
      await execute("Removing menu item", async () => {
        await api(`/menu/${button.dataset.menuItemId}`, {
          method: "DELETE",
        });
        state.notice = "Today's menu updated.";
        await refreshRoleData();
      });
    });
  });

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

function bindSalesEvents() {
  document.querySelector("#sales-year")?.addEventListener("change", async (event) => {
    const year = Number(event.currentTarget.value);
    const [, currentMonth] = parseMonthValue(state.salesSelectedMonth || getCurrentMonthValue());
    const validMonths = getSalesMonthOptionsForYear(year);
    const fallbackMonth = validMonths.some((entry) => entry.month === currentMonth)
      ? currentMonth
      : validMonths[validMonths.length - 1].month;
    state.salesSelectedMonth = buildMonthValue(year, fallbackMonth);
    await execute("Loading sales month", async () => {
      await refreshRoleData();
    });
  });

  document.querySelector("#sales-month")?.addEventListener("change", async (event) => {
    const month = Number(event.currentTarget.value);
    const [year] = parseMonthValue(state.salesSelectedMonth || getCurrentMonthValue());
    state.salesSelectedMonth = buildMonthValue(year, month);
    await execute("Loading sales month", async () => {
      await refreshRoleData();
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

  document.querySelector("#print-bill-btn")?.addEventListener("click", async (event) => {
    const orderId = Number(event.currentTarget.dataset.orderId);
    const payload = collectBillingForm();
    await execute("Printing bill", async () => {
      const result = await api(`/reception/orders/${orderId}/print-bill`, {
        method: "POST",
        body: payload,
      });
      state.billing = result.snapshot || state.billing;
      state.notice = buildPrintBillNotice(result);
      await refreshRoleData();
    });
  });

  document.querySelector("#checkout-btn")?.addEventListener("click", async (event) => {
    const orderId = Number(event.currentTarget.dataset.orderId);
    const payload = collectBillingForm();
    const paymentMethod = document.querySelector("#payment_method").value;
    const paymentNotes = document.querySelector("#payment_notes").value.trim() || null;
    await execute("Completing payment", async () => {
      const result = await api(`/reception/orders/${orderId}/checkout`, {
        method: "POST",
        body: {
          items: payload.items,
          discount: payload.discount,
          payment_method: paymentMethod,
          notes: paymentNotes,
        },
      });
      state.selectedReceptionOrderId = null;
      state.notice = buildCheckoutNotice(result);
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

async function logout() {
  if (state.token) {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      // Ignore logout failures and clear local state anyway.
    }
  }
  if (state.socket) {
    state.socket.close();
  }
  clearSession();
  state.tables = [];
  state.kitchenTables = [];
  state.menuItems = [];
  state.selectedTable = null;
  state.selectedTableId = null;
  state.selectedSeatNumbers = [];
  state.pendingBills = [];
  state.selectedReceptionOrder = null;
  state.selectedReceptionOrderId = null;
  state.billing = null;
  state.receptionSalesToday = null;
  state.receptionSalesWeek = null;
  state.salesMonth = null;
  state.salesSelectedMonth = null;
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

  if (state.user.role === "sales") {
    const [today, week] = await Promise.all([
      api("/sales/reports/sales?days=1"),
      api("/sales/reports/sales?days=7"),
    ]);
    if (!state.salesSelectedMonth) {
      state.salesSelectedMonth = formatMonthValue(today.end_date);
    }
    const { startDate, endDate } = getMonthDateRange(state.salesSelectedMonth);
    const month = await api(`/sales/reports/sales?start_date=${startDate}&end_date=${endDate}`);
    state.receptionSalesToday = today;
    state.receptionSalesWeek = week;
    state.salesMonth = month;
    state.tables = [];
    state.menuItems = [];
    state.pendingBills = [];
    state.selectedTable = null;
    state.selectedTableId = null;
    state.selectedSeatNumbers = [];
    state.selectedReceptionOrder = null;
    state.selectedReceptionOrderId = null;
    state.billing = null;
    render();
    return;
  }

  if (state.user.role === "kitchen") {
    const [kitchenTables, menuItems] = await Promise.all([api("/kitchen/active"), api("/menu")]);
    state.kitchenTables = kitchenTables;
    state.menuItems = menuItems;
    state.receptionSalesToday = null;
    state.receptionSalesWeek = null;
    state.salesMonth = null;
    state.salesSelectedMonth = null;
    render();
    return;
  }

  if (state.user.role === "receptionist") {
    const [tables, pendingBills] = await Promise.all([
      api("/tables"),
      api("/reception/orders/pending"),
    ]);
    state.tables = tables;
    state.menuItems = [];
    state.pendingBills = pendingBills;
    state.receptionSalesToday = null;
    state.receptionSalesWeek = null;
    state.salesMonth = null;
    state.salesSelectedMonth = null;
  } else {
    const [tables, menuItems] = await Promise.all([api("/tables"), api("/menu")]);
    state.tables = tables;
    state.menuItems = menuItems;
    state.pendingBills = [];
    state.selectedReceptionOrder = null;
    state.selectedReceptionOrderId = null;
    state.receptionSalesToday = null;
    state.receptionSalesWeek = null;
    state.salesMonth = null;
    state.salesSelectedMonth = null;
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
    item_name: row.querySelector(".js-item-name").value.trim(),
    note: row.querySelector(".js-item-note").value.trim() || null,
    source_status: row.querySelector(".js-source-status").value,
    consumed_quantity: Number(row.querySelector(".js-consumed-quantity").textContent.trim() || 0),
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

function buildCheckoutNotice(result) {
  if (result?.receipt_printed === true) {
    return "Payment recorded. Receipt printed.";
  }
  if (result?.receipt_printed === false) {
    return `Payment recorded, but receipt printing failed: ${result.receipt_message}`;
  }
  return "Payment recorded. The bill is closed.";
}

function buildPrintBillNotice(result) {
  if (result?.receipt_printed === true) {
    return "Bill printed.";
  }
  if (result?.receipt_printed === false) {
    return `Bill saved, but printing failed: ${result.receipt_message}`;
  }
  return "Bill saved.";
}

async function execute(label, work, options = {}) {
  const scrollAnchor = captureScrollAnchor(options.scrollAnchorSelector);
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
    restoreScrollAnchor(scrollAnchor);
  }
}

function captureScrollAnchor(selector) {
  if (window.innerWidth > 1100) {
    return null;
  }
  const anchor = selector ? document.querySelector(selector) : document.querySelector("#table-detail-panel");
  if (!anchor) {
    return null;
  }
  return {
    selector,
    topOffset: anchor.getBoundingClientRect().top,
  };
}

function restoreScrollAnchor(anchorState) {
  if (!anchorState || window.innerWidth > 1100) {
    return;
  }
  window.setTimeout(() => {
    const selector = anchorState.selector || "#table-detail-panel";
    const anchor = document.querySelector(selector) || document.querySelector("#table-detail-panel");
    if (!anchor) {
      return;
    }
    const nextTop = window.scrollY + anchor.getBoundingClientRect().top - anchorState.topOffset;
    window.scrollTo({ top: Math.max(nextTop, 0), behavior: "auto" });
  }, 60);
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

  state.socket.onclose = (event) => {
    if (!state.user) {
      return;
    }
    if (event.code === 1008) {
      invalidateSession("This account was opened somewhere else. Please sign in again.");
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
    if (response.status === 401 && options.authenticated !== false) {
      invalidateSession(message);
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
  if (type === "menu_updated") {
    const actionLabel = payload?.action === "deleted" ? "removed" : "updated";
    const itemLabel = payload?.item_name ? ` ${payload.item_name}.` : "";
    return `Today's menu ${actionLabel}.${itemLabel}`;
  }
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
    return "This table has pending seat checks waiting at reception. Select the table to open and settle them here.";
  }
  if (table.status === "empty") {
    return "No current service on this table right now.";
  }
  return "Waiter is still serving this table. Pending seat checks will show here after the waiter sends them to reception.";
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

function invalidateSession(message) {
  if (state.socket) {
    state.socket.close();
  }
  clearSession();
  state.tables = [];
  state.kitchenTables = [];
  state.menuItems = [];
  state.selectedTable = null;
  state.selectedTableId = null;
  state.selectedSeatNumbers = [];
  state.pendingBills = [];
  state.selectedReceptionOrder = null;
  state.selectedReceptionOrderId = null;
  state.billing = null;
  state.receptionSalesToday = null;
  state.receptionSalesWeek = null;
  state.salesMonth = null;
  state.salesSelectedMonth = null;
  state.notice = "";
  state.error = message;
  state.busy = "";
  render();
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

function compareDateAsc(left, right) {
  const leftTime = left ? new Date(left).getTime() : 0;
  const rightTime = right ? new Date(right).getTime() : 0;
  return leftTime - rightTime;
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

function formatDateLabel(value) {
  if (!value) {
    return "Unknown";
  }
  const normalized = typeof value === "string" && value.length === 10 ? `${value}T00:00:00` : value;
  return new Date(normalized).toLocaleDateString([], {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatMiniDateLabel(value) {
  if (!value) {
    return "--";
  }
  const normalized = typeof value === "string" && value.length === 10 ? `${value}T00:00:00` : value;
  return new Date(normalized).toLocaleDateString([], {
    day: "2-digit",
    month: "short",
  });
}

function getCurrentMonthValue() {
  const now = new Date();
  return buildMonthValue(now.getFullYear(), now.getMonth() + 1);
}

function buildMonthValue(year, month) {
  return `${year}-${String(month).padStart(2, "0")}`;
}

function parseMonthValue(value) {
  const [year, month] = String(value || getCurrentMonthValue()).split("-").map((part) => Number(part));
  return [year, month];
}

function formatMonthValue(value) {
  const [year, month] = parseMonthValue(String(value).slice(0, 7));
  return buildMonthValue(year, month);
}

function formatMonthHeading(value) {
  const [year, month] = parseMonthValue(value);
  return new Date(year, month - 1, 1).toLocaleDateString([], {
    month: "short",
    year: "numeric",
  });
}

function getSalesYearOptions() {
  const currentYear = new Date().getFullYear();
  const years = [];
  for (let year = 2026; year <= currentYear; year += 1) {
    years.push(year);
  }
  return years;
}

function getSalesMonthOptionsForYear(year) {
  const current = new Date();
  const minMonth = year === 2026 ? 4 : 1;
  const maxMonth = year === current.getFullYear() ? current.getMonth() + 1 : 12;
  const labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const months = [];
  for (let month = minMonth; month <= maxMonth; month += 1) {
    months.push({ month, label: labels[month - 1] });
  }
  return months;
}

function getMonthDateRange(monthValue) {
  const [year, month] = parseMonthValue(monthValue);
  const startDate = `${year}-${String(month).padStart(2, "0")}-01`;
  const lastDay = new Date(year, month, 0).getDate();
  const endDate = `${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;
  return { startDate, endDate };
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
