// Shared header. Renders logged-in vs logged-out nav, the theme toggle, and
// wires logout.
import { auth, api } from "./api.js";
import { savedTheme, applyTheme, nextTheme } from "./theme.js";
import { esc } from "./ui.js";

const LINKS = [
  { href: "/app/index.html", label: "Browse", always: true },
  { href: "/app/report.html", label: "Report an item", authOnly: true },
  { href: "/app/claims.html", label: "Claims", authOnly: true },
  { href: "/app/admin.html", label: "Admin", adminOnly: true },
];

// A luggage tag on its string: the brand mark.
const BRAND_MARK = `
  <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true" focusable="false">
    <path d="M9 3h12a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H9l-5-5V8z" fill="currentColor"/>
    <circle cx="8.6" cy="13" r="2.2" fill="var(--surface)"/>
    <path d="M13 9h6M13 13h4M13 17h5" stroke="var(--surface)" stroke-width="1.6" stroke-linecap="round"/>
  </svg>`;

const THEME_UI = {
  system: {
    name: "System",
    icon: '<rect x="2" y="3" width="12" height="8.5" rx="1.2"/><path d="M5.5 14h5M8 11.5V14"/>',
  },
  light: {
    name: "Light",
    icon: '<circle cx="8" cy="8" r="3"/><path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1"/>',
  },
  dark: {
    name: "Dark",
    icon: '<path d="M13.2 10.2A5.6 5.6 0 0 1 5.8 2.8a5.6 5.6 0 1 0 7.4 7.4z"/>',
  },
};

function themeButton() {
  const current = savedTheme();
  const ui = THEME_UI[current];
  const next = THEME_UI[nextTheme(current)].name;
  return `
    <button type="button" class="secondary small theme-toggle" data-theme-toggle
            data-testid="theme-toggle" data-current="${current}"
            aria-label="Colour theme: ${ui.name}. Switch to ${next}." title="Theme: ${ui.name} (switch to ${next})">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${ui.icon}</svg>
      <span class="theme-name" aria-hidden="true">${ui.name}</span>
    </button>`;
}

export function renderNav() {
  const mount = document.querySelector("[data-nav]");
  if (!mount) return;

  const here = window.location.pathname;
  const loggedIn = auth.isLoggedIn;
  const user = auth.user;

  // `is_admin` comes off the stored login payload; the API re-checks it on
  // every admin call, so hiding the link is convenience, not security.
  const isAdmin = Boolean(loggedIn && user && user.is_admin);
  const link = (href, label) =>
    `<a href="${href}"${here === href ? ' class="active" aria-current="page"' : ""}>${label}</a>`;
  const links = LINKS.filter(
    (l) => l.always || (l.authOnly && loggedIn) || (l.adminOnly && isAdmin)
  ).map((l) => link(l.href, l.label));
  if (!loggedIn) {
    links.push(link("/app/login.html", "Log in"), link("/app/register.html", "Register"));
  }

  const account = loggedIn
    ? `<span class="whoami" data-whoami>${user ? esc(`${user.first_name} ${user.last_name}`) : "Signed in"}</span>
       <button class="secondary small" data-logout type="button">Log out</button>`
    : "";

  mount.innerHTML = `
    <a class="skip-link button small" href="#main">Skip to content</a>
    <div class="inner">
      <a class="brand" href="/app/index.html">${BRAND_MARK}<span>Campus Lost &amp; Found</span></a>
      <nav class="links" aria-label="Main">${links.join("")}</nav>
      <div class="nav-tools">${account}${themeButton()}</div>
    </div>`;

  const logout = mount.querySelector("[data-logout]");
  if (logout) {
    logout.addEventListener("click", () => {
      auth.clear();
      window.location.href = "/app/login.html";
    });
  }

  mount.querySelector("[data-theme-toggle]").addEventListener("click", () => {
    applyTheme(nextTheme(savedTheme()));
    renderNav();
    mount.querySelector("[data-theme-toggle]").focus(); // keep keyboard place
  });
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
