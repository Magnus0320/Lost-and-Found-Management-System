// Shared header. Renders logged-in vs logged-out nav and wires logout.
import { auth, api } from "./api.js";

const LINKS = [
  { href: "/app/index.html", label: "Browse", always: true },
  { href: "/app/report.html", label: "Report an item", authOnly: true },
  { href: "/app/claims.html", label: "Claims", authOnly: true },
  { href: "/app/admin.html", label: "Admin", adminOnly: true },
];

export function renderNav() {
  const mount = document.querySelector("[data-nav]");
  if (!mount) return;

  const here = window.location.pathname;
  const loggedIn = auth.isLoggedIn;
  const user = auth.user;

  // `is_admin` comes off the stored login payload; the API re-checks it on
  // every admin call, so hiding the link is convenience, not security.
  const isAdmin = Boolean(loggedIn && user && user.is_admin);
  const links = LINKS.filter(
    (l) => l.always || (l.authOnly && loggedIn) || (l.adminOnly && isAdmin)
  )
    .map(
      (l) =>
        `<a href="${l.href}" class="${here === l.href ? "active" : ""}">${l.label}</a>`
    )
    .join("");

  const right = loggedIn
    ? `<span class="whoami" data-whoami>${user ? `${user.first_name} ${user.last_name}` : "Signed in"}</span>
       <button class="secondary small" data-logout type="button">Log out</button>`
    : `<a href="/app/login.html">Log in</a>
       <a href="/app/register.html">Register</a>`;

  mount.innerHTML = `
    <div class="inner">
      <a class="brand" href="/app/index.html">Campus Lost &amp; Found</a>
      <nav>${links}${right}</nav>
    </div>`;

  const logout = mount.querySelector("[data-logout]");
  if (logout) {
    logout.addEventListener("click", () => {
      auth.clear();
      window.location.href = "/app/login.html";
    });
  }
}

/**
 * Re-read the signed-in user from the API and re-render if anything changed.
 *
 * The stored login payload is a snapshot taken at sign-in: it goes stale the
 * moment the account changes underneath it. Granting someone admin would not
 * show them the link until they logged out and back in -- and, worse, revoking
 * it would leave the link sitting there. Refreshing on every page load keeps
 * the nav honest in both directions.
 *
 * It is cosmetic either way: the API re-checks the role on every admin call,
 * so a stale `is_admin: true` opens nothing.
 */
async function syncUser() {
  if (!auth.isLoggedIn) return;
  try {
    const fresh = await api.me();
    const before = JSON.stringify(auth.user);
    if (JSON.stringify(fresh) !== before) {
      auth.save(auth.token, fresh);
      renderNav();
    }
  } catch {
    /* offline, or the token expired -- request() already handles a 401 */
  }
}

document.addEventListener("DOMContentLoaded", () => {
  renderNav();   // paint immediately from the cached payload, then verify
  syncUser();
});
