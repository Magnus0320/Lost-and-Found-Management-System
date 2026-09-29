// Small rendering helpers shared across pages.

export function pill(value) {
  if (!value) return "";
  return `<span class="pill pill-${value}">${value}</span>`;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

export function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString();
}

export function day(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleDateString();
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

/** "<status pill> | contact X at x@y" -- the status with its contact, if any. */
export function statusWithContact(status, user, opts) {
  const contact = contactLine(user, opts);
  return contact ? `${pill(status)} <span class="sep">|</span> ${contact}` : pill(status);
}
