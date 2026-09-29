import { api, auth, showError, clearError, showNotice, requireLogin } from "../api.js";
import { pill, esc, when, statusWithContact, emptyState, skeletonRows, busy } from "../ui.js";

if (requireLogin()) {
  const incoming = document.querySelector("[data-incoming]");
  const outgoing = document.querySelector("[data-outgoing]");

  function claimCard(c, item, withActions) {
    // Whose address matters depends on which side of the claim you are on: the
    // reporter needs the claimant, the claimant needs the reporter. Either way
    // it is only there once the API has approved the disclosure.
    const other = withActions ? c.claimant : c.reporter;
    const name = c.item_name || (item ? item.name : "Item #" + c.item_id);
    return `
      <div class="claim" data-claim-id="${c.id}" data-testid="claim-row">
        <div class="spread">
          <span class="who">
            <a href="/app/item.html?id=${c.item_id}">${esc(name)}</a>
          </span>
          <span data-testid="claim-status-${c.id}">${statusWithContact(c.status, other)}</span>
        </div>
        <div class="muted small-text" style="margin-top:4px">
          ${withActions
            ? `Claimed by ${esc(c.claimant.first_name)} ${esc(c.claimant.last_name)}`
            : `Reported by ${c.reporter ? esc(c.reporter.first_name + " " + c.reporter.last_name) : "—"}
               · Item status: ${item ? pill(item.status) : "—"}`}
        </div>
        <p class="evidence">${esc(c.evidence)}</p>
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
    if (!target.children.length) target.innerHTML = skeletonRows(2);
    busy(target, true);
    let results;
    try {
      ({ results } = await api.listClaims({ mine_only: mineOnly, limit: 100 }));
    } finally {
      busy(target, false);
    }
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

    // The claim carries its item's reporter, so splitting the two directions
    // no longer depends on the item fetch above having succeeded.
    const me = auth.user;
    const rows = results.filter((c) =>
      ownedByMe ? Boolean(me && c.reporter && c.reporter.id === me.id) : true
    );

    target.innerHTML = rows.length
      ? rows.map((c) => claimCard(c, items.get(c.item_id), ownedByMe)).join("")
      : emptyState(
          ownedByMe
            ? { art: "box", title: "No claims on your items",
                body: "When someone says an item you reported is theirs, it lands here for you to decide." }
            : { art: "tag", title: "You haven't claimed anything",
                body: "Spotted your lost item in the log? Open it and file a claim with your proof.",
                action: '<a class="button secondary" href="/app/index.html">Browse the log</a>' }
        );
    return rows.length;
  }

  async function refresh() {
    clearError();
    try {
      // The API only ever returns claims I am a party to. `mine_only=true` is
      // the ones I filed; the unscoped list is split client-side into the
      // claims filed against items I reported.
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
