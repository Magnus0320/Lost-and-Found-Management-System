import { api, auth, showError, clearError, showNotice, requireLogin, ApiError } from "../api.js";
import { pill, esc, logDate, skeletonRows, emptyState } from "../ui.js";

const PAGE = 50;

// Where a row reports what happened to it. Always present (and live), so
// screen readers announce the text when it changes; empty, it takes no space.
const STATUS_SLOT = `<p class="row-status" data-row-status aria-live="polite"></p>`;

if (requireLogin()) {
  const el = {
    denied: document.querySelector("[data-denied]"),
    admin: document.querySelector("[data-admin]"),
    stats: document.querySelector("[data-stats]"),
    items: document.querySelector("[data-items]"),
    itemsCount: document.querySelector("[data-items-count]"),
    itemFilter: document.querySelector("[data-item-filter]"),
    selectAll: document.querySelector("[data-select-all]"),
    bulkDelete: document.querySelector("[data-bulk-delete]"),
    users: document.querySelector("[data-users]"),
    usersCount: document.querySelector("[data-users-count]"),
    userFilter: document.querySelector("[data-user-filter]"),
    locations: document.querySelector("[data-locations]"),
    categories: document.querySelector("[data-categories]"),
  };

  let itemQuery = { limit: PAGE, offset: 0 };
  let userQuery = { limit: PAGE, offset: 0 };
  let lastItemTotal = 0;

  // --- rendering ----------------------------------------------------------

  function renderStats(s) {
    const tiles = [
      ["Items", s.items], ["Accounts", s.users],
      ["Claims", s.claims], ["Admins", s.admins],
    ];
    el.stats.innerHTML = tiles
      .map(([label, n]) => `<div class="stat"><b>${Number(n).toLocaleString()}</b><span>${esc(label)}</span></div>`)
      .join("");
  }

  function renderItems(data) {
    disarmWithin(el.items, el.bulkDelete); // the rows (and the selection) are replaced
    lastItemTotal = data.total;
    el.items.innerHTML = data.results.length
      ? data.results
          .map(
            (i) => `
        <div class="adminrow" data-testid="admin-item-row">
          <label class="inline">
            <input type="checkbox" data-item-check value="${i.id}">
            <span class="idno"><span class="sr-only">Select item </span>#${i.id}</span>
          </label>
          <div class="grow">
            <a class="row-name" href="/app/item.html?id=${i.id}">${esc(i.name)}</a>
            ${pill(i.kind)} ${pill(i.status)}
            <div class="sub-line">
              ${esc(i.reporter.first_name)} ${esc(i.reporter.last_name)}
              (#${i.reporter.id}) · <span class="mono">${logDate(i.occurred_on)}</span>
            </div>
          </div>
          <span class="buttons">
            <button type="button" class="danger small" data-del-item="${i.id}">Delete</button>
          </span>
          ${STATUS_SLOT}
        </div>`
          )
          .join("")
      : emptyState({ art: "search", title: "No items match", body: "Try another search or reset the filters." });

    const from = data.total ? itemQuery.offset + 1 : 0;
    const to = Math.min(itemQuery.offset + data.results.length, data.total);
    el.itemsCount.textContent = `${from}–${to} of ${data.total}`;
    el.selectAll.checked = false;
    syncBulkButton();
  }

  function renderUsers(data) {
    disarmWithin(el.users);
    const me = auth.user;
    el.users.innerHTML = data.results.length
      ? data.results
          .map(
            (u) => `
        <div class="adminrow" data-testid="admin-user-row">
          <span class="idno">#${u.id}</span>
          <div class="grow">
            <span class="row-name">${esc(u.first_name)} ${esc(u.last_name)}</span>
            ${u.is_admin ? `<span class="pill chip tone-ok">admin</span>` : ""}
            ${u.is_verified ? "" : `<span class="pill chip tone-warn">unverified</span>`}
            <div class="sub-line">
              ${esc(u.email)} · ${esc(u.roll_number)} · ${esc(u.course)} ${esc(u.branch)} ${u.batch}
            </div>
          </div>
          ${
            me && u.id === me.id
              ? `<span class="muted small-text">that's you</span>`
              : `<span class="buttons"><button type="button" class="secondary small" data-role="${u.id}"
                         data-make="${u.is_admin ? "false" : "true"}">
                   ${u.is_admin ? "Revoke admin" : "Make admin"}
                 </button>
                 <button type="button" class="danger small" data-del-user="${u.id}"
                         ${u.is_admin ? "disabled title='Revoke admin first'" : ""}>Delete</button></span>`
          }
          ${STATUS_SLOT}
        </div>`
          )
          .join("")
      : emptyState({ art: "search", title: "No accounts match", body: "Search by email, name or roll number." });
    el.usersCount.textContent = `${data.results.length} shown of ${data.total}`;
  }

  function renderRefData(locations, categories) {
    disarmWithin(el.locations, el.categories);
    el.locations.innerHTML = locations.results.length
      ? locations.results
          .map(
            (l) => `<div class="adminrow">
              <div class="grow"><span class="row-name">${esc(l.name)}</span>
                ${l.building ? `<span class="muted small-text">(${esc(l.building)})</span>` : ""}</div>
              <span class="buttons">
                <button type="button" class="danger small" data-del-location="${l.id}">Delete</button>
              </span>
              ${STATUS_SLOT}
            </div>`
          )
          .join("")
      : `<p class="muted">None yet.</p>`;

    el.categories.innerHTML = categories.results.length
      ? categories.results
          .map(
            (c) => `<div class="adminrow">
              <div class="grow"><span class="row-name">${esc(c.name)}</span></div>
              <span class="buttons">
                <button type="button" class="danger small" data-del-category="${c.id}">Delete</button>
              </span>
              ${STATUS_SLOT}
            </div>`
          )
          .join("")
      : `<p class="muted">None yet.</p>`;
  }

  // --- loading ------------------------------------------------------------

  async function loadItems() {
    renderItems(await api.searchItems(itemQuery));
  }

  async function loadUsers() {
    renderUsers(await api.adminUsers(userQuery));
  }

  async function refreshStats() {
    renderStats(await api.adminStats());
  }

  async function refresh() {
    clearError();
    const [stats, , , locations, categories] = await Promise.all([
      api.adminStats(), loadItems(), loadUsers(),
      api.listLocations(), api.listCategories(),
    ]);
    renderStats(stats);
    renderRefData(locations, categories);
  }

  // --- selection ----------------------------------------------------------

  function checked() {
    return [...el.items.querySelectorAll("[data-item-check]:checked")].map((c) =>
      Number(c.value)
    );
  }

  function syncBulkButton() {
    const n = checked().length;
    el.bulkDelete.disabled = n === 0;
    el.bulkDelete.textContent = n ? `Delete selected (${n})` : "Delete selected";
  }

  el.items.addEventListener("change", (e) => {
    if (!e.target.matches("[data-item-check]")) return;
    if (armed?.btn === el.bulkDelete) disarm();
    syncBulkButton();
  });

  el.selectAll.addEventListener("change", () => {
    if (armed?.btn === el.bulkDelete) disarm();
    el.items
      .querySelectorAll("[data-item-check]")
      .forEach((c) => (c.checked = el.selectAll.checked));
    syncBulkButton();
  });

  // --- two-step delete ------------------------------------------------------
  // No window.confirm(): the first click arms the button in place -- it turns
  // into "Confirm delete" with a Cancel beside it, and a hint in the row says
  // what will go. Only a second click deletes. It disarms by itself after
  // CONFIRM_MS, on Cancel or Escape, or when another Delete is armed.
  //
  // Results are reported next to the row, not only in the notice at the top,
  // which is out of view once the admin has scrolled down. A deleted row stays
  // put, struck through, until the next refresh, so the message stays with it.

  const CONFIRM_MS = 5000;
  let armed = null; // { btn, cancel, label, timer }

  function statusSlot(anchor) {
    return anchor.closest(".adminrow, .toolbar")?.querySelector("[data-row-status]");
  }

  function setRowStatus(anchor, text, tone) {
    const slot = statusSlot(anchor);
    if (!slot) return null;
    slot.textContent = text || "";
    slot.dataset.tone = tone || "";
    return slot;
  }

  function arm(btn, { confirmLabel = "Confirm delete", hint }) {
    disarm();
    clearError();
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "secondary small";
    cancel.textContent = "Cancel";
    cancel.dataset.cancelDelete = "";
    btn.after(cancel);
    armed = { btn, cancel, label: btn.textContent.trim(), timer: setTimeout(disarm, CONFIRM_MS) };
    btn.textContent = confirmLabel;
    btn.classList.add("armed");
    setRowStatus(btn, `${hint} Confirm within ${CONFIRM_MS / 1000} seconds, or cancel.`, "hint");
  }

  /** Put an armed button back as it was. Returns it, or null if none was armed. */
  function disarm() {
    if (!armed) return null;
    const { btn, cancel, label, timer } = armed;
    armed = null;
    clearTimeout(timer);
    const hadFocus = cancel === document.activeElement;
    cancel.remove();
    btn.textContent = label;
    btn.classList.remove("armed");
    if (statusSlot(btn)?.dataset.tone === "hint") setRowStatus(btn, "", "");
    if (hadFocus) btn.focus(); // keyboard users keep their place
    return btn;
  }

  /** Disarm if the armed button is about to be re-rendered away. */
  function disarmWithin(...containers) {
    if (armed && containers.some((c) => c === armed.btn || c.contains(armed.btn))) disarm();
  }

  /** The second click: stop the countdown and show that work is under way. */
  function commit(btn) {
    const { cancel, label, timer } = armed;
    armed = null;
    clearTimeout(timer);
    cancel.remove();
    btn.classList.remove("armed");
    btn.disabled = true;
    btn.textContent = "Deleting…";
    setRowStatus(btn, "", "");
    return label;
  }

  function restore(btn, label) {
    btn.disabled = false;
    btn.textContent = label;
  }

  /** Mark a row as deleted in place, with the message beside it. */
  function markDeleted(row, message, { focus = true } = {}) {
    row.classList.add("is-deleted");
    row.querySelector(".buttons")?.remove();
    const check = row.querySelector("[data-item-check]");
    if (check) {
      check.checked = false;
      check.disabled = true;
      check.removeAttribute("data-item-check"); // out of select-all and bulk delete
    }
    row.querySelectorAll(".grow a").forEach((a) => {
      const span = document.createElement("span");
      span.className = a.className;
      span.textContent = a.textContent;
      a.replaceWith(span);
    });
    const slot = setRowStatus(row, message, "ok");
    if (focus && slot) {
      slot.tabIndex = -1; // the button that had focus is gone; land on the result
      slot.focus();
    }
  }

  function failed(btn, label, err) {
    restore(btn, label);
    setRowStatus(btn, err.message, "error");
    showError(err);
    btn.focus();
  }

  const DELETES = {
    delItem: {
      hint: (id) => `Item #${id} will be deleted for good.`,
      run: (id) => api.adminDeleteItem(id),
      done: (id) => `Item #${id} deleted.`,
      after: () => refreshStats(),
    },
    delUser: {
      hint: (id) => `Account #${id} and everything it reported will be deleted.`,
      run: (id) => api.adminDeleteUser(id),
      done: (id) => `Account #${id} deleted.`,
      // Its items went with it (ON DELETE CASCADE), so the item list is stale.
      after: () => Promise.all([refreshStats(), loadItems()]),
    },
    delLocation: {
      hint: () => "This location will be deleted. Items keep existing without it.",
      run: (id) => api.adminDeleteLocation(id),
      done: () => "Location deleted.",
    },
    delCategory: {
      hint: () => "This category will be deleted. Items keep existing without it.",
      run: (id) => api.adminDeleteCategory(id),
      done: () => "Category deleted.",
    },
  };

  async function deleteRow(btn, key) {
    const spec = DELETES[key];
    const id = btn.dataset[key];
    if (armed?.btn !== btn) {
      arm(btn, { hint: spec.hint(id) });
      return;
    }
    const label = commit(btn);
    const row = btn.closest(".adminrow");
    try {
      await spec.run(id);
    } catch (err) {
      failed(btn, label, err);
      return;
    }
    const message = spec.done(id);
    markDeleted(row, message);
    showNotice(message, "ok");
    try {
      if (spec.after) await spec.after();
    } catch (err) {
      showError(err); // the delete itself went through
    }
  }

  el.bulkDelete.addEventListener("click", async () => {
    const btn = el.bulkDelete;
    const ids = checked();
    if (!ids.length) return;
    if (armed?.btn !== btn) {
      arm(btn, {
        confirmLabel: `Confirm delete (${ids.length})`,
        hint: `${ids.length} item(s) will be deleted for good.`,
      });
      return;
    }
    const label = commit(btn);
    let res;
    try {
      res = await api.adminBulkDeleteItems(ids);
    } catch (err) {
      failed(btn, label, err);
      syncBulkButton();
      return;
    }
    for (const id of ids) {
      const row = el.items.querySelector(`[data-item-check][value="${id}"]`)?.closest(".adminrow");
      if (row) markDeleted(row, `Item #${id} deleted.`, { focus: false });
    }
    el.selectAll.checked = false;
    restore(btn, label);
    syncBulkButton();
    const slot = setRowStatus(btn, res.detail, "ok");
    slot.tabIndex = -1;
    slot.focus();
    showNotice(res.detail, "ok");
    refreshStats().catch((err) => showError(err));
  });

  async function changeRole(btn) {
    clearError();
    const d = btn.dataset;
    btn.disabled = true;
    try {
      await api.adminSetRole(d.role, { is_admin: d.make === "true" });
      showNotice(d.make === "true" ? "Admin access granted." : "Admin access revoked.", "ok");
      await refresh();
    } catch (err) {
      showError(err);
    } finally {
      btn.disabled = false;
    }
  }

  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-cancel-delete]")) {
      disarm()?.focus();
      return;
    }
    const role = e.target.closest("[data-role]");
    if (role) {
      changeRole(role);
      return;
    }
    const btn = e.target.closest("[data-del-item],[data-del-user],[data-del-location],[data-del-category]");
    if (!btn) return;
    deleteRow(btn, Object.keys(DELETES).find((k) => k in btn.dataset));
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && armed) disarm()?.focus();
  });

  // --- filters and paging -------------------------------------------------

  el.itemFilter.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(el.itemFilter);
    itemQuery = { limit: PAGE, offset: 0 };
    for (const k of ["q", "status", "reporter_id"]) {
      const v = (f.get(k) || "").toString().trim();
      if (v) itemQuery[k] = v;
    }
    try { await loadItems(); } catch (err) { showError(err); }
  });

  document.querySelector("[data-item-reset]").addEventListener("click", async () => {
    el.itemFilter.reset();
    itemQuery = { limit: PAGE, offset: 0 };
    try { await loadItems(); } catch (err) { showError(err); }
  });

  el.userFilter.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = (new FormData(el.userFilter).get("q") || "").toString().trim();
    userQuery = q ? { limit: PAGE, offset: 0, q } : { limit: PAGE, offset: 0 };
    try { await loadUsers(); } catch (err) { showError(err); }
  });

  document.querySelector("[data-user-reset]").addEventListener("click", async () => {
    el.userFilter.reset();
    userQuery = { limit: PAGE, offset: 0 };
    try { await loadUsers(); } catch (err) { showError(err); }
  });

  document.querySelector("[data-page-prev]").addEventListener("click", async () => {
    if (itemQuery.offset === 0) return;
    itemQuery.offset = Math.max(0, itemQuery.offset - PAGE);
    try { await loadItems(); } catch (err) { showError(err); }
  });

  document.querySelector("[data-page-next]").addEventListener("click", async () => {
    if (itemQuery.offset + PAGE >= lastItemTotal) return;
    itemQuery.offset += PAGE;
    try { await loadItems(); } catch (err) { showError(err); }
  });

  document.querySelector("[data-refresh]").addEventListener("click", () => {
    disarm();
    refresh().catch((err) => showError(err));
  });

  // --- boot ---------------------------------------------------------------
  el.items.innerHTML = skeletonRows(3);
  el.users.innerHTML = skeletonRows(2);
  // The stored login payload says whether this account is staff, but the API
  // is the authority: a 403 from /admin/stats is what actually gates the page.
  refresh()
    .then(() => { el.admin.hidden = false; })
    .catch((err) => {
      if (err instanceof ApiError && err.status === 403) {
        el.denied.hidden = false;
      } else {
        el.admin.hidden = false;
        showError(err);
      }
    });
}
