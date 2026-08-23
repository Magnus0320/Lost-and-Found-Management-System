import { api, auth, showError, clearError, showNotice, formData, qs, ApiError } from "../api.js";
import { pill, esc, when, day } from "../ui.js";

// Mirrors app/lifecycle.py ALLOWED_TRANSITIONS so the UI only offers moves the
// API will accept. The API remains the authority: it re-validates every move.
const ALLOWED = {
  reported: ["matched", "closed"],
  matched: ["claimed", "reported", "closed"],
  claimed: ["closed", "matched"],
  closed: [],
};

const itemId = qs("id");
const el = {
  item: document.querySelector("[data-item]"),
  ownerPanel: document.querySelector("[data-owner-panel]"),
  buttons: document.querySelector("[data-transition-buttons]"),
  claimPanel: document.querySelector("[data-claim-panel]"),
  claimForm: document.querySelector("[data-claim-form]"),
  claimsPanel: document.querySelector("[data-item-claims-panel]"),
  claims: document.querySelector("[data-item-claims]"),
  history: document.querySelector("[data-history]"),
};

let current = null;

function renderItem(item) {
  current = item;
  document.querySelector('[data-testid="item-name"]').textContent = item.name;
  document.querySelector('[data-testid="item-status"]').innerHTML = pill(item.status);
  document.querySelector("[data-item-kindline]").innerHTML =
    `${pill(item.kind)} <span class="muted">· reported ${day(item.created_at)}</span>`;
  document.querySelector('[data-testid="item-description"]').textContent = item.description;
  document.querySelector('[data-testid="item-location"]').textContent = item.location
    ? item.location.name + (item.location.building ? ` (${item.location.building})` : "")
    : "—";
  document.querySelector('[data-testid="item-category"]').textContent =
    item.category ? item.category.name : "—";
  document.querySelector('[data-testid="item-date"]').textContent = day(item.occurred_on);
  document.querySelector('[data-testid="item-reporter"]').textContent =
    `${item.reporter.first_name} ${item.reporter.last_name}`;
  el.item.hidden = false;

  el.history.innerHTML = (item.status_events || [])
    .map(
      (e) => `<li>
        ${e.from_status ? `${pill(e.from_status)} &rarr; ` : ""}${pill(e.to_status)}
        ${e.note ? `<div>${esc(e.note)}</div>` : ""}
        <div class="when">${when(e.created_at)}</div>
      </li>`
    )
    .join("") || `<li class="muted">No history yet.</li>`;

  const me = auth.user;
  const isOwner = Boolean(me && me.id === item.reporter.id);

  // Owner: lifecycle controls
  el.ownerPanel.hidden = !isOwner;
  if (isOwner) {
    const moves = ALLOWED[item.status] || [];
    el.buttons.innerHTML = moves.length
      ? moves
          .map(
            (s) =>
              `<button type="button" class="${s === "closed" ? "secondary" : ""}"
                 data-transition="${s}" data-testid="transition-${s}">Mark ${s}</button>`
          )
          .join("")
      : `<p class="muted">This item is closed. No further changes.</p>`;
  }

  // Non-owner: claim form, only while the item is still open
  const canClaim = Boolean(me) && !isOwner && item.status !== "closed";
  el.claimPanel.hidden = !canClaim;

  // Owner: claims filed on this item
  el.claimsPanel.hidden = !isOwner;
  if (isOwner) loadClaims();
}

async function loadClaims() {
  try {
    const data = await api.listClaims({ item_id: itemId, limit: 100 });
    el.claims.innerHTML = data.results.length
      ? data.results
          .map(
            (c) => `
        <div class="claim" data-claim-id="${c.id}" data-testid="claim-row">
          <div class="spread">
            <span class="who">${esc(c.claimant.first_name)} ${esc(c.claimant.last_name)}</span>
            <span data-testid="claim-status-${c.id}">${pill(c.status)}</span>
          </div>
          <p class="muted" style="margin:6px 0 0">${esc(c.evidence)}</p>
          <div class="when">${when(c.created_at)}</div>
          ${
            c.status === "pending"
              ? `<div class="actions">
                   <button class="small" data-decide="${c.id}" data-approve="true"
                           data-testid="approve-${c.id}">Approve</button>
                   <button class="small danger" data-decide="${c.id}" data-approve="false"
                           data-testid="reject-${c.id}">Reject</button>
                 </div>`
              : ""
          }
        </div>`
          )
          .join("")
      : `<p class="muted">No claims filed yet.</p>`;
  } catch (err) {
    if (!(err instanceof ApiError && err.status === 401)) showError(err);
  }
}

/** Re-fetch and re-render in place, so status changes appear without a reload. */
async function refresh() {
  const item = await api.getItem(itemId);
  renderItem(item);
  return item;
}

// --- events ---------------------------------------------------------------

el.buttons?.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-transition]");
  if (!btn) return;
  clearError();
  btn.disabled = true;
  try {
    const updated = await api.transitionStatus(itemId, { to_status: btn.dataset.transition });
    renderItem(updated); // response is the full ItemDetailResponse
    showNotice(`Status is now "${updated.status}".`, "ok");
  } catch (err) {
    showError(err);
    btn.disabled = false;
  }
});

el.claims?.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-decide]");
  if (!btn) return;
  clearError();
  btn.disabled = true;
  try {
    await api.decideClaim(btn.dataset.decide, { approve: btn.dataset.approve === "true" });
    await refresh(); // item status may have moved to 'claimed'
    showNotice(
      btn.dataset.approve === "true" ? "Claim approved." : "Claim rejected.",
      "ok"
    );
  } catch (err) {
    showError(err);
    btn.disabled = false;
  }
});

el.claimForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError(el.claimForm);
  const btn = el.claimForm.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    await api.fileClaim(itemId, formData(el.claimForm));
    el.claimForm.reset();
    await refresh(); // filing a claim moves 'reported' -> 'matched'
    showNotice("Claim filed. The reporter has been notified.", "ok");
    el.claimPanel.hidden = true;
  } catch (err) {
    showError(err, el.claimForm);
  } finally {
    btn.disabled = false;
  }
});

// --- boot -----------------------------------------------------------------

if (!itemId) {
  showError(new Error("No item id given."));
} else {
  refresh().catch((err) => showError(err));
}
