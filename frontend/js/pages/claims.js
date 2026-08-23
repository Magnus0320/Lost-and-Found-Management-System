import { api, auth, showError, clearError, showNotice, requireLogin } from "../api.js";
import { pill, esc, when } from "../ui.js";

if (requireLogin()) {
  const incoming = document.querySelector("[data-incoming]");
  const outgoing = document.querySelector("[data-outgoing]");

  function claimCard(c, item, withActions) {
    return `
      <div class="claim" data-claim-id="${c.id}" data-testid="claim-row">
        <div class="spread">
          <span class="who">
            <a href="/app/item.html?id=${c.item_id}">${esc(item ? item.name : "Item #" + c.item_id)}</a>
          </span>
          <span data-testid="claim-status-${c.id}">${pill(c.status)}</span>
        </div>
        <div class="muted" style="font-size:13px;margin-top:4px">
          ${withActions
            ? `Claimed by ${esc(c.claimant.first_name)} ${esc(c.claimant.last_name)}`
            : `Item status: ${item ? pill(item.status) : "—"}`}
        </div>
        <p style="margin:8px 0 0">${esc(c.evidence)}</p>
        <div class="when">${when(c.created_at)}</div>
        ${
          withActions && c.status === "pending"
            ? `<div class="actions">
                 <button class="small" data-decide="${c.id}" data-approve="true"
                         data-testid="approve-${c.id}">Approve</button>
                 <button class="small danger" data-decide="${c.id}" data-approve="false"
                         data-testid="reject-${c.id}">Reject</button>
               </div>`
            : ""
        }
      </div>`;
  }

  /** Fetch claims and the items they belong to, so each row can show context. */
  async function loadInto(target, { mineOnly, ownedByMe }) {
    const { results } = await api.listClaims({ mine_only: mineOnly, limit: 100 });
    const items = new Map();
    await Promise.all(
      [...new Set(results.map((c) => c.item_id))].map(async (id) => {
        try {
          items.set(id, await api.getItem(id));
        } catch {
          /* item may have been deleted; the row still renders */
        }
      })
    );

    const me = auth.user;
    const rows = results.filter((c) => {
      const item = items.get(c.item_id);
      if (ownedByMe) return item && me && item.reporter.id === me.id;
      return true;
    });

    target.innerHTML = rows.length
      ? rows.map((c) => claimCard(c, items.get(c.item_id), ownedByMe)).join("")
      : `<p class="muted">Nothing here yet.</p>`;
    return rows.length;
  }

  async function refresh() {
    clearError();
    try {
      // `mine_only=true` scopes to claims I filed; the unscoped list is filtered
      // client-side down to items I reported, since the API has no owner filter.
      await loadInto(outgoing, { mineOnly: true, ownedByMe: false });
      await loadInto(incoming, { mineOnly: false, ownedByMe: true });
    } catch (err) {
      showError(err);
    }
  }

  incoming.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-decide]");
    if (!btn) return;
    clearError();
    const approve = btn.dataset.approve === "true";
    btn.disabled = true;
    try {
      await api.decideClaim(btn.dataset.decide, { approve });
      await refresh(); // re-render in place; item status may now be 'claimed'
      showNotice(approve ? "Claim approved. Item is now claimed." : "Claim rejected.", "ok");
    } catch (err) {
      showError(err);
      btn.disabled = false;
    }
  });

  document.querySelector("[data-refresh]").addEventListener("click", refresh);
  refresh();
}
