import { api, auth, showError, clearError, showNotice, formData, qs, ApiError } from "../api.js";
import { pill, esc, when, day, contactLine, statusWithContact, statusLabel } from "../ui.js";

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
  myClaimPanel: document.querySelector("[data-my-claim-panel]"),
  myClaim: document.querySelector("[data-my-claim]"),
  claimsPanel: document.querySelector("[data-item-claims-panel]"),
  claims: document.querySelector("[data-item-claims]"),
  history: document.querySelector("[data-history]"),
  suggestionsPanel: document.querySelector("[data-suggestions-panel]"),
  suggestionsIntro: document.querySelector("[data-suggestions-intro]"),
  suggestions: document.querySelector("[data-suggestions]"),
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
  // The address is only present once this viewer's claim has been approved;
  // otherwise contactLine() renders nothing and just the name shows.
  const reporterContact = contactLine(item.reporter, { withName: false });
  document.querySelector('[data-testid="item-reporter"]').innerHTML =
    `${esc(item.reporter.first_name)} ${esc(item.reporter.last_name)}` +
    (reporterContact ? `<div class="contact-row">${reporterContact}</div>` : "");
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
                 data-transition="${s}" data-testid="transition-${s}">Mark ${esc(statusLabel(s).toLowerCase())}</button>`
          )
          .join("")
      : `<p class="muted">This item is closed. No further changes.</p>`;
  }

  // Non-owner: claim form, only while the item is still open. loadMyClaim()
  // takes the form away again if they have already filed one.
  const canClaim = Boolean(me) && !isOwner && item.status !== "closed";
  el.claimPanel.hidden = !canClaim;

  // Non-owner: the outcome of the claim they filed, if any.
  el.myClaimPanel.hidden = true;
  if (me && !isOwner) loadMyClaim();

  // Owner: claims filed on this item
  el.claimsPanel.hidden = !isOwner;
  if (isOwner) loadClaims();

  loadSuggestions(item);
}

/** Open posts of the opposite kind that read like this one. Public data only:
 *  the API never attaches contact details to a suggestion. */
async function loadSuggestions(item) {
  const other = item.kind === "lost" ? "found" : "lost";
  el.suggestionsIntro.textContent =
    item.kind === "lost"
      ? "Found items that look like this one. If one is yours, open it and file a claim."
      : "Lost reports that look like this item. The owner may be one of them.";
  el.suggestionsPanel.hidden = false;

  if (item.status === "closed") {
    el.suggestions.innerHTML = `<p class="muted" data-testid="no-suggestions">This item is closed, so no matches are suggested.</p>`;
    return;
  }
  try {
    const { results } = await api.itemSuggestions(item.id);
    el.suggestions.innerHTML = results.length
      ? results.map(renderSuggestion).join("")
      : `<p class="muted" data-testid="no-suggestions">No similar ${other} items yet. Check back later.</p>`;
  } catch (err) {
    showError(err);
  }
}

function renderSuggestion(s) {
  const meta = [
    s.location ? s.location.name : null,
    day(s.occurred_on),
    ...s.reasons,
  ].filter(Boolean);
  return `
    <a class="suggestion" href="/app/item.html?id=${s.id}" data-testid="suggestion">
      <div class="spread">
        <span class="name">${esc(s.name)}</span>
        <span>${pill(s.status)} ${pill(s.kind)}</span>
      </div>
      <div class="meta">${meta.map(esc).join(" · ")}</div>
    </a>`;
}

/** The viewer's own claim on this item -- its decision, and who to contact. */
async function loadMyClaim() {
  try {
    const { results } = await api.listClaims({ item_id: itemId, mine_only: true, limit: 1 });
    const mine = results[0];
    if (!mine) return;

    // They have already filed; the form would only ever return 409.
    el.claimPanel.hidden = true;
    el.myClaimPanel.hidden = false;

    const outcome = {
      pending: "Waiting for the reporter to decide.",
      approved: "Approved — arrange the handover with the reporter.",
      rejected: "The reporter rejected this claim.",
    }[mine.status] || "";

    el.myClaim.innerHTML = `
      <div class="spread">
        <span data-testid="my-claim-status">${statusWithContact(mine.status, mine.reporter)}</span>
        <span class="when">${when(mine.created_at)}</span>
      </div>
      <p class="muted" style="margin:8px 0 0">${esc(outcome)}</p>
      <p style="margin:8px 0 0">${esc(mine.evidence)}</p>`;
  } catch (err) {
    if (!(err instanceof ApiError && err.status === 401)) showError(err);
  }
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
            <span data-testid="claim-status-${c.id}">${statusWithContact(c.status, c.claimant, { withName: false })}</span>
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
    showNotice(`Status is now "${statusLabel(updated.status)}".`, "ok");
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
