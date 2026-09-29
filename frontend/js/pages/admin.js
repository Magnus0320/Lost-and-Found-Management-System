import { api, auth, showError, clearError, showNotice, requireLogin, ApiError } from "../api.js";
import { pill, esc, when, day } from "../ui.js";

const PAGE = 50;

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
      .map(([label, n]) => `<div class="stat"><b>${n}</b><span>${esc(label)}</span></div>`)
      .join("");
  }

  function renderItems(data) {
    lastItemTotal = data.total;
    el.items.innerHTML = data.results.length
      ? data.results
          .map(
            (i) => `
        <div class="adminrow" data-testid="admin-item-row">
          <label class="inline">
            <input type="checkbox" data-item-check value="${i.id}">
            <span class="mono">#${i.id}</span>
          </label>
          <div class="grow">
            <a href="/app/item.html?id=${i.id}">${esc(i.name)}</a>
            ${pill(i.status)} ${pill(i.kind)}
            <div class="muted" style="font-size:12.5px">
              ${esc(i.reporter.first_name)} ${esc(i.reporter.last_name)}
              (#${i.reporter.id}) · ${day(i.occurred_on)}
            </div>
          </div>
          <button type="button" class="danger small" data-del-item="${i.id}">Delete</button>
        </div>`
          )
          .join("")
      : `<p class="muted">No items match.</p>`;

    const from = data.total ? itemQuery.offset + 1 : 0;
    const to = Math.min(itemQuery.offset + data.results.length, data.total);
    el.itemsCount.textContent = `${from}–${to} of ${data.total}`;
    el.selectAll.checked = false;
    syncBulkButton();
  }

  function renderUsers(data) {
    const me = auth.user;
    el.users.innerHTML = data.results.length
      ? data.results
          .map(
            (u) => `
        <div class="adminrow" data-testid="admin-user-row">
          <span class="mono">#${u.id}</span>
          <div class="grow">
            ${esc(u.first_name)} ${esc(u.last_name)}
            ${u.is_admin ? `<span class="pill pill-approved">admin</span>` : ""}
            ${u.is_verified ? "" : `<span class="pill pill-pending">unverified</span>`}
            <div class="muted" style="font-size:12.5px">
              ${esc(u.email)} · ${esc(u.roll_number)} · ${esc(u.course)} ${esc(u.branch)} ${u.batch}
            </div>
          </div>
          ${
            me && u.id === me.id
              ? `<span class="muted" style="font-size:12.5px">that's you</span>`
              : `<button type="button" class="secondary small" data-role="${u.id}"
                         data-make="${u.is_admin ? "false" : "true"}">
                   ${u.is_admin ? "Revoke admin" : "Make admin"}
                 </button>
                 <button type="button" class="danger small" data-del-user="${u.id}"
                         ${u.is_admin ? "disabled title='Revoke admin first'" : ""}>Delete</button>`
          }
        </div>`
          )
          .join("")
      : `<p class="muted">No accounts match.</p>`;
    el.usersCount.textContent = `${data.results.length} shown of ${data.total}`;
  }

  function renderRefData(locations, categories) {
    el.locations.innerHTML = locations.results.length
      ? locations.results
          .map(
            (l) => `<div class="adminrow">
              <div class="grow">${esc(l.name)}
                ${l.building ? `<span class="muted">(${esc(l.building)})</span>` : ""}</div>
              <button type="button" class="danger small" data-del-location="${l.id}">Delete</button>
            </div>`
          )
          .join("")
      : `<p class="muted">None yet.</p>`;

    el.categories.innerHTML = categories.results.length
      ? categories.results
          .map(
            (c) => `<div class="adminrow">
              <div class="grow">${esc(c.name)}</div>
              <button type="button" class="danger small" data-del-category="${c.id}">Delete</button>
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
    if (e.target.matches("[data-item-check]")) syncBulkButton();
  });

  el.selectAll.addEventListener("change", () => {
    el.items
      .querySelectorAll("[data-item-check]")
      .forEach((c) => (c.checked = el.selectAll.checked));
    syncBulkButton();
  });

  // --- actions ------------------------------------------------------------

  el.bulkDelete.addEventListener("click", async () => {
    const ids = checked();
    if (!ids.length) return;
    if (!confirm(`Delete ${ids.length} item(s)? This cannot be undone.`)) return;
    el.bulkDelete.disabled = true;
    try {
      const res = await api.adminBulkDeleteItems(ids);
      await refresh();
      showNotice(res.detail, "ok");
    } catch (err) {
      showError(err);
    } finally {
      syncBulkButton();
    }
  });

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(
      "[data-del-item],[data-del-user],[data-role],[data-del-location],[data-del-category]"
    );
    if (!btn) return;
    clearError();
    const d = btn.dataset;
    try {
      btn.disabled = true;
      if (d.delItem) {
        if (!confirm(`Delete item #${d.delItem}?`)) return;
        await api.adminDeleteItem(d.delItem);
        showNotice(`Item #${d.delItem} deleted.`, "ok");
      } else if (d.delUser) {
        if (!confirm(`Delete account #${d.delUser} and everything it reported?`)) return;
        await api.adminDeleteUser(d.delUser);
        showNotice(`Account #${d.delUser} deleted.`, "ok");
      } else if (d.role) {
        await api.adminSetRole(d.role, { is_admin: d.make === "true" });
        showNotice(d.make === "true" ? "Admin access granted." : "Admin access revoked.", "ok");
      } else if (d.delLocation) {
        if (!confirm("Delete this location? Items keep existing without it.")) return;
        await api.adminDeleteLocation(d.delLocation);
        showNotice("Location deleted.", "ok");
      } else if (d.delCategory) {
        if (!confirm("Delete this category? Items keep existing without it.")) return;
        await api.adminDeleteCategory(d.delCategory);
        showNotice("Category deleted.", "ok");
      }
      await refresh();
    } catch (err) {
      showError(err);
    } finally {
      btn.disabled = false;
    }
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

  document.querySelector("[data-refresh]").addEventListener("click", () =>
    refresh().catch((err) => showError(err))
  );

  // --- boot ---------------------------------------------------------------
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
