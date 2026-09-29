import { api, showError, clearError } from "../api.js";
import {
  pill, esc, logDate, itemNo, ICON, emptyState, skeletonCards, busy,
} from "../ui.js";

const form = document.querySelector("[data-search-form]");
const results = document.querySelector("[data-results]");
const empty = document.querySelector("[data-empty]");
const count = document.querySelector("[data-result-count]");
const counts = document.querySelector("[data-counts]");

function card(item) {
  const where = item.location ? item.location.name : "Location not given";
  return `
    <a class="card" href="/app/item.html?id=${item.id}" data-testid="item-card"
       data-item-id="${item.id}" data-kind="${esc(item.kind)}">
      <span class="hole" aria-hidden="true"></span>
      <div class="tag-stub"><span>${itemNo(item.id)}</span><span>${logDate(item.occurred_on)}</span></div>
      <h3>${esc(item.name)}</h3>
      <div class="labels">${pill(item.kind)} ${pill(item.status)}</div>
      <p class="desc">${esc(item.description)}</p>
      <div class="meta">
        <span>${ICON.pin} ${esc(where)}</span>
        ${item.category ? `<span>${ICON.tag} ${esc(item.category.name)}</span>` : ""}
      </div>
    </a>`;
}

function filtered(params) {
  return ["q", "status", "kind", "category_id"].some((k) => params[k]);
}

async function search() {
  clearError();
  const params = Object.fromEntries(new FormData(form).entries());
  params.limit = 50;

  results.innerHTML = skeletonCards(6);
  empty.hidden = true;
  busy(results, true);
  try {
    const data = await api.searchItems(params);
    results.innerHTML = data.results.map(card).join("");
    empty.hidden = data.results.length > 0;
    if (!data.results.length) {
      empty.innerHTML = filtered(params)
        ? emptyState({
            art: "search",
            title: "Nothing in the log matches that",
            body: "Try fewer words, or clear a filter. New items are logged all the time.",
            action: '<button type="button" class="secondary" data-empty-reset>Clear search</button>',
          })
        : emptyState({
            art: "tag",
            title: "The log is empty",
            body: "No items have been reported yet. Found something on campus? Log it first.",
            action: '<a class="button" href="/app/report.html">Report an item</a>',
          });
    }
    count.textContent = data.total
      ? `${data.total} item${data.total === 1 ? "" : "s"}` +
        (data.total > data.results.length ? ` · showing ${data.results.length}` : "")
      : "";
    count.setAttribute("data-total", data.total);
  } catch (err) {
    results.innerHTML = "";
    showError(err);
  } finally {
    busy(results, false);
  }
}

/** Live totals for the intro band, from the public search endpoint. */
async function loadCounts() {
  const total = (status) => api.searchItems({ status, limit: 1 }).then((r) => r.total);
  try {
    const [reported, matched, claimed, closed] = await Promise.all(
      ["reported", "matched", "claimed", "closed"].map(total)
    );
    const set = (key, n) => {
      counts.querySelector(`[data-count="${key}"]`).textContent = n.toLocaleString();
    };
    set("total", reported + matched + claimed + closed);
    set("open", reported + matched);
    set("reunited", claimed + closed); // an owner has been confirmed, or it is resolved
  } catch {
    counts.hidden = true; // decoration: the page works without it
  } finally {
    busy(counts, false);
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
function reset() {
  form.reset();
  search();
}
document.querySelector("[data-reset]").addEventListener("click", reset);
empty.addEventListener("click", (e) => {
  if (e.target.closest("[data-empty-reset]")) reset();
});

// Support deep-linking a query, e.g. /app/index.html?q=wallet
const initial = new URLSearchParams(window.location.search).get("q");
if (initial) form.querySelector('[name="q"]').value = initial;

loadCounts();
loadCategories();
search();
