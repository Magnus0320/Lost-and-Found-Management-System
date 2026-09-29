// Small rendering helpers shared across pages.

// How a value reads in the UI, where that differs from the API value. The API
// keeps 'matched'; to a visitor it means someone has claimed the item and the
// reporter has not decided yet.
const LABELS = { matched: "Claim pending" };

export function statusLabel(value) {
  return LABELS[value] || value;
}

/**
 * A small label for an API value. Lost/found render as coloured chips; every
 * status (item or claim) renders as a rubber stamp. `.pill` and `data-value`
 * are stable hooks for tests and styles alike.
 */
export function pill(value, { large = false } = {}) {
  if (!value) return "";
  const kind = value === "lost" || value === "found";
  const cls = kind ? "pill kind" : `pill stamp${large ? " stamp-lg" : ""}`;
  return `<span class="${cls}" data-value="${esc(value)}">${esc(statusLabel(value))}</span>`;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// A bare YYYY-MM-DD is a calendar date, not a UTC instant: `new Date()` would
// read it as midnight UTC and show the previous day west of Greenwich.
function parseDate(iso) {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
  return isNaN(d) ? null : d;
}

export function when(iso) {
  const d = parseDate(iso);
  return d ? d.toLocaleString() : iso || "";
}

export function day(iso) {
  const d = parseDate(iso);
  return d ? d.toLocaleDateString() : iso || "";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "14 Sep 2026" -- the fixed-width style of a property log. */
export function logDate(iso) {
  const d = parseDate(iso);
  if (!d) return "";
  return `${String(d.getDate()).padStart(2, "0")} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** "No. 00042" */
export function itemNo(id) {
  return `No. ${String(id).padStart(5, "0")}`;
}

/** Just the address, as a mailto link -- "" when it was not disclosed. */
export function contactLink(user) {
  if (!user || !user.contact_email) return "";
  const mail = esc(user.contact_email);
  return `<a href="mailto:${mail}">${mail}</a>`;
}

/**
 * Contact details for the other party, once the API has disclosed them.
 *
 * `contact_email` is present only on an approved claim, and only for the two
 * people it is between -- so rendering it unconditionally is safe: when the
 * viewer is not entitled, the field is simply not there.
 *
 * Pass `withName: false` where the person's name is already on the same line,
 * so it does not read "Asha Rao ... Contact Asha Rao at ...".
 */
export function contactLine(user, { withName = true } = {}) {
  const link = contactLink(user);
  if (!link) return "";
  const name = `${user.first_name} ${user.last_name}`.trim();
  const prefix = withName ? `Contact ${esc(name)} at ` : "";
  return `<span class="contact" data-testid="contact-line">${prefix}${link}</span>`;
}

/** "<status stamp> | contact X at x@y" -- the status with its contact, if any. */
export function statusWithContact(status, user, opts) {
  const contact = contactLine(user, opts);
  return contact ? `${pill(status)} <span class="sep" aria-hidden="true">|</span> ${contact}` : pill(status);
}

// --- icons ------------------------------------------------------------------
// Decorative: the text beside each one says the same thing.
const svg = (body, size = 14) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" ` +
  `stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${body}</svg>`;

export const ICON = {
  pin: svg('<path d="M8 14.5s4.5-4.2 4.5-7.7A4.5 4.5 0 0 0 3.5 6.8c0 3.5 4.5 7.7 4.5 7.7z"/><circle cx="8" cy="6.8" r="1.6"/>'),
  tag: svg('<path d="M2 8.6V2.8c0-.5.3-.8.8-.8h5.8l5.6 5.6a1 1 0 0 1 0 1.4l-4.4 4.4a1 1 0 0 1-1.4 0z"/><circle cx="5.3" cy="5.3" r="1"/>'),
  back: svg('<path d="M10 3 5 8l5 5"/>', 16),
  check: svg('<path d="m3.5 8.5 3 3 6-7"/>', 16),
};

// --- empty states -------------------------------------------------------------
// Original line drawings, themed through currentColor and the CSS tokens.
const ART = {
  // A blank luggage tag on a loose string.
  tag: `
    <svg width="120" height="88" viewBox="0 0 120 88" fill="none" aria-hidden="true" focusable="false">
      <path d="M8 76c10-4 16-14 24-24" stroke="var(--accent)" stroke-width="2.2" stroke-linecap="round" stroke-dasharray="2 5"/>
      <g transform="rotate(-9 70 44)">
        <path d="M46 22h54a6 6 0 0 1 6 6v32a6 6 0 0 1-6 6H46L32 52V36z" fill="var(--card)" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
        <circle cx="42" cy="44" r="4.5" fill="var(--bg)" stroke="currentColor" stroke-width="2"/>
        <path d="M58 36h34M58 44h24M58 52h30" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity=".35"/>
      </g>
    </svg>`,
  // A magnifier over an empty ledger line.
  search: `
    <svg width="120" height="88" viewBox="0 0 120 88" fill="none" aria-hidden="true" focusable="false">
      <path d="M14 70h92" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-dasharray="3 6" opacity=".45"/>
      <rect x="22" y="14" width="46" height="40" rx="5" fill="var(--card)" stroke="currentColor" stroke-width="2"/>
      <path d="M31 26h26M31 34h18M31 42h22" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity=".35"/>
      <circle cx="74" cy="46" r="15" fill="var(--surface)" stroke="currentColor" stroke-width="2.4"/>
      <path d="M85 57l12 12" stroke="var(--accent)" stroke-width="5" stroke-linecap="round"/>
      <path d="M70 42.5a4.5 4.5 0 1 1 5.6 4.4c-1 .3-1.6 1.1-1.6 2.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <circle cx="74" cy="53.5" r="1.3" fill="currentColor"/>
    </svg>`,
  // An open lost-property box with a tag hanging off it.
  box: `
    <svg width="120" height="88" viewBox="0 0 120 88" fill="none" aria-hidden="true" focusable="false">
      <path d="M28 36l32 8 32-8v34l-32 9-32-9z" fill="var(--card)" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
      <path d="M60 44v35" stroke="currentColor" stroke-width="2"/>
      <path d="M28 36 16 24l32-8 12 12zM92 36l12-12-32-8-12 12z" fill="var(--surface)" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
      <path d="M86 52c6 2 9 6 10 11" stroke="var(--accent)" stroke-width="2" stroke-linecap="round"/>
      <path d="M92 62h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H92l-4-6z" fill="var(--card)" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
    </svg>`,
};

export function emptyState({ art = "tag", title, body = "", action = "" }) {
  return `
    <div class="empty" data-testid="empty-state">
      ${ART[art] || ""}
      <p class="title">${esc(title)}</p>
      ${body ? `<p>${esc(body)}</p>` : ""}
      ${action ? `<div class="actions">${action}</div>` : ""}
    </div>`;
}

// --- loading skeletons ------------------------------------------------------------
// Shapes only: the container they go in is marked aria-busy while loading.

export function skeletonCards(n = 6) {
  const one = `
    <div class="card skeleton" aria-hidden="true">
      <span class="hole"></span>
      <div class="tag-stub"><span class="skel" style="height:11px;width:45%"></span></div>
      <span class="skel skel-title"></span>
      <span class="skel skel-line" style="width:38%"></span>
      <span class="skel skel-line"></span>
      <span class="skel skel-line" style="width:82%"></span>
    </div>`;
  return one.repeat(n);
}

export function skeletonRows(n = 2) {
  const one = `
    <div class="claim" aria-hidden="true">
      <span class="skel skel-line" style="width:55%;margin-top:2px"></span>
      <span class="skel skel-line" style="width:30%"></span>
      <span class="skel skel-line" style="width:85%;margin-bottom:2px"></span>
    </div>`;
  return one.repeat(n);
}

/** Mark a region as loading (or not) for assistive technology. */
export function busy(el, on) {
  if (!el) return;
  if (on) el.setAttribute("aria-busy", "true");
  else el.removeAttribute("aria-busy");
}

/**
 * Show a development-mode one-time code. The code comes from the URL or the
 * API, so it is set as text, never parsed as HTML.
 */
export function showDevCode(box, code) {
  box.textContent = "Development mode: no email was sent. Your code is ";
  const c = document.createElement("code");
  c.dataset.testid = "dev-otp-value";
  c.textContent = code;
  box.appendChild(c);
  box.hidden = false;
}
