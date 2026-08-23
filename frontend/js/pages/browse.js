import { api, showError, clearError } from "../api.js";
import { pill, esc, day } from "../ui.js";

const form = document.querySelector("[data-search-form]");
const results = document.querySelector("[data-results]");
const empty = document.querySelector("[data-empty]");
const count = document.querySelector("[data-result-count]");

function card(item) {
  return `
    <a class="card" href="/app/item.html?id=${item.id}" data-testid="item-card" data-item-id="${item.id}">
      <h3>${esc(item.name)}</h3>
      <div>${pill(item.status)} ${pill(item.kind)}</div>
      <p class="desc">${esc(item.description)}</p>
      <div class="meta">
        ${item.location ? esc(item.location.name) : "Location not given"}
        · ${day(item.occurred_on)}
        ${item.category ? "· " + esc(item.category.name) : ""}
      </div>
    </a>`;
}

async function search() {
  clearError();
  const params = Object.fromEntries(new FormData(form).entries());
  params.limit = 50;
  try {
    const data = await api.searchItems(params);
    results.innerHTML = data.results.map(card).join("");
    empty.hidden = data.results.length > 0;
    count.textContent = data.total
      ? `${data.total} item${data.total === 1 ? "" : "s"} found` +
        (data.total > data.results.length ? ` (showing ${data.results.length})` : "")
      : "";
    count.setAttribute("data-total", data.total);
  } catch (err) {
    showError(err);
  }
}

async function loadCategories() {
  try {
    const { results: cats } = await api.listCategories();
    const sel = form.querySelector('[name="category_id"]');
    for (const c of cats) {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = c.name;
      sel.appendChild(o);
    }
  } catch {
    /* categories are a nice-to-have filter; search still works without them */
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  search();
});
document.querySelector("[data-reset]").addEventListener("click", () => {
  form.reset();
  search();
});

// Support deep-linking a query, e.g. /app/index.html?q=wallet
const initial = new URLSearchParams(window.location.search).get("q");
if (initial) form.querySelector('[name="q"]').value = initial;

loadCategories();
search();
