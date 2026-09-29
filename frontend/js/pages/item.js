import { api, auth, showError, clearError, showNotice, formData, qs, ApiError } from "../api.js";
import {
  pill, esc, when, logDate, itemNo, contactLine, statusWithContact, statusLabel,
  ICON, emptyState, skeletonRows, busy,
} from "../ui.js";

// Mirrors app/lifecycle.py ALLOWED_TRANSITIONS so the UI only offers moves the
// API will accept. The API remains the authority: it re-validates every move.
const ALLOWED = {
  reported: ["matched", "closed"],
  matched: ["claimed", "reported", "closed"],
  claimed: ["closed", "matched"],
  closed: [],
};
const STEPS = ["reported", "matched", "claimed", "closed"];

const itemId = qs("id");
const el = {
  skeleton: document.querySelector("[data-item-skeleton]"),
  item: document.querySelector("[data-item]"),
  ownerPanel: document.querySelector("[data-owner-panel]"),
  buttons: document.querySelector("[data-transition-buttons]"),
  claimPanel: document.querySelector("[data-claim-panel]"),
  claimForm: document.querySelector("[data-claim-form]"),
  myClaimPanel: document.querySelector("[data-my-claim-panel]"),
  myClaim: document.querySelector("[data-my-claim]"),
  claimsPanel: document.querySelector("[data-item-claims-panel]"),
  claims: document.querySelector("[data-item-claims]"),
  stepper: document.querySelector("[data-stepper]"),
  history: document.querySelector("[data-history]"),
  suggestionsPanel: document.querySelector("[data-suggestions-panel]"),
  suggestionsIntro: document.querySelector("[data-suggestions-intro]"),
  suggestions: document.querySelector("[data-suggestions]"),
};

document.querySelector("[data-back]").innerHTML = `${ICON.back} Back to the property log`;

let current = null;

function renderItem(item) {
  current = item;
  document.title = `${item.name} — Campus Lost & Found`;
  el.item.dataset.kind = item.kind;
  el.item.querySelector("[data-item-no]").textContent = itemNo(item.id);
  el.item.querySelector("[data-item-logged]").textContent = `Logged ${logDate(item.created_at)}`;
  document.querySelector('[data-testid="item-name"]').textContent = item.name;
  document.querySelector('[data-testid="item-status"]').innerHTML = pill(item.status, { large: true });
  document.querySelector("[data-item-kindline]").innerHTML = pill(item.kind);
  document.querySelector('[data-testid="item-description"]').textContent = item.description;
  document.querySelector('[data-testid="item-location"]').textContent = item.location
    ? item.location.name + (item.location.building ? ` (${item.location.building})` : "")
    : "—";
  document.querySelector('[data-testid="item-category"]').textContent =
    item.category ? item.category.name : "—";
  document.querySelector("[data-date-label]").textContent =
    item.kind === "lost" ? "Lost on" : "Found on";
  const date = document.querySelector('[data-testid="item-date"]');
  date.textContent = logDate(item.occurred_on);
  date.className = "mono";
  // The address is only present once this viewer's claim has been approved;
  // otherwise contactLine() renders nothing and just the name shows.
  const reporterContact = contactLine(item.reporter, { withName: false });
  document.querySelector('[data-testid="item-reporter"]').innerHTML =
    `${esc(item.reporter.first_name)} ${esc(item.reporter.last_name)}` +
    (reporterContact ? `<div class="contact-row">${reporterContact}</div>` : "");
  el.skeleton.hidden = true;
  el.item.hidden = false;

  renderStepper(item);
  el.history.innerHTML = (item.status_events || [])
    .map(
      (e) => `<li>
        <div class="move">
          ${e.from_status ? `${pill(e.from_status)} <span aria-hidden="true">&rarr;</span><span class="sr-only">to</span> ` : ""}${pill(e.to_status)}
        </div>
        ${e.note ? `<div class="note">${esc(e.note)}</div>` : ""}
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
    // One orange button: the next step forward. Corrections and closing early
    // are available, but quieter.
    const forward = STEPS[STEPS.indexOf(item.status) + 1];
    el.buttons.innerHTML = moves.length
      ? moves
          .map(
            (s) =>
              `<button type="button" class="${s === forward ? "" : "secondary"}"
                 data-transition="${s}" data-testid="transition-${s}">Mark ${esc(statusLabel(s).toLowerCase())}</button>`
          )
          .join("")
      : `<p class="muted" style="margin:0">This item is closed. No further changes.</p>`;
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

/**
 * Where the item is on reported -> claim pending -> claimed -> closed.
 * Steps it passed through are "done"; steps it jumped over (reported straight
 * to closed, say) are "skipped", read from its own history.
 */
function renderStepper(item) {
  const visited = new Set((item.status_events || []).map((e) => e.to_status));
  const at = STEPS.indexOf(item.status);
  el.stepper.innerHTML = STEPS.map((step, i) => {
    let state, note;
    if (i === at) {
      state = item.status === "closed" ? "done current" : "current";
      note = "Now";
    } else if (i < at) {
      [state, note] = visited.has(step) ? ["done", "Done"] : ["skipped", "Skipped"];
    } else {
      [state, note] = ["todo", "Not yet"];
    }
    const mark = state.startsWith("done") ? ICON.check : state === "skipped" ? "&ndash;" : i + 1;
    // Arriving here straight past a skipped step: draw that line dashed too.
    const jump = i > 0 && i <= at && !visited.has(STEPS[i - 1]) ? " jump" : "";
    return `<li class="${state}${jump}"${i === at ? ' aria-current="step"' : ""}>
      <span class="dot" aria-hidden="true">${mark}</span>
      <span class="label">${esc(statusLabel(step)[0].toUpperCase() + statusLabel(step).slice(1))}</span>
      <span class="state">${note}</span>
    </li>`;
  }).join("");
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
    el.suggestions.innerHTML = emptyState({
      art: "tag",
      title: "This item is closed",
      body: "It has been resolved, so no matches are suggested.",
    });
    return;
  }
  el.suggestions.innerHTML = skeletonRows(2);
  busy(el.suggestions, true);
  try {
    const { results } = await api.itemSuggestions(item.id);
    el.suggestions.innerHTML = results.length
      ? results.map(renderSuggestion).join("")
      : emptyState({
          art: "search",
          title: `No similar ${other} items yet`,
          body: "The office checks every new report against this one. Check back later.",
        });
  } catch (err) {
    el.suggestions.innerHTML = "";
    showError(err);
  } finally {
    busy(el.suggestions, false);
  }
}

function renderSuggestion(s) {
  return `
    <a class="suggestion" href="/app/item.html?id=${s.id}" data-testid="suggestion" data-kind="${esc(s.kind)}">
      <div class="spread">
        <span class="name">${esc(s.name)}</span>
        <span>${pill(s.kind)} ${pill(s.status)}</span>
      </div>
      <div class="meta">
        ${s.location ? `<span>${ICON.pin} ${esc(s.location.name)}</span>` : ""}
        <span class="mono">${logDate(s.occurred_on)}</span>
        ${s.reasons.length ? `<span class="why">${s.reasons.map(esc).join(" · ")}</span>` : ""}
      </div>
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
      <p class="muted" style="margin:10px 0 0">${esc(outcome)}</p>
      <p class="evidence">${esc(mine.evidence)}</p>`;
  } catch (err) {
    if (!(err instanceof ApiError && err.status === 401)) showError(err);
  }
}

async function loadClaims() {
  if (!el.claims.children.length) el.claims.innerHTML = skeletonRows(1);
  busy(el.claims, true);
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
          <p class="evidence">${esc(c.evidence)}</p>
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
      : emptyState({
          art: "box",
          title: "No claims yet",
          body: "When someone says this is theirs, their claim and evidence appear here for you to decide.",
        });
  } catch (err) {
    el.claims.innerHTML = "";
    if (!(err instanceof ApiError && err.status === 401)) showError(err);
  } finally {
    busy(el.claims, false);
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

function failed(err) {
  el.skeleton.hidden = true;
  showError(err);
}

if (!itemId) {
  failed(new Error("No item id given."));
} else {
  refresh().catch(failed);
}
