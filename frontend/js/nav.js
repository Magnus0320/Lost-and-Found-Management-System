// Shared header. Renders logged-in vs logged-out nav and wires logout.
import { auth } from "./api.js";

const LINKS = [
  { href: "/app/index.html", label: "Browse", always: true },
  { href: "/app/report.html", label: "Report an item", authOnly: true },
  { href: "/app/claims.html", label: "Claims", authOnly: true },
];

export function renderNav() {
  const mount = document.querySelector("[data-nav]");
  if (!mount) return;

  const here = window.location.pathname;
  const loggedIn = auth.isLoggedIn;
  const user = auth.user;

  const links = LINKS.filter((l) => l.always || (l.authOnly && loggedIn))
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

document.addEventListener("DOMContentLoaded", renderNav);
