import { api, showError, clearError, formData, requireLogin } from "../api.js";

if (requireLogin()) {
  const form = document.querySelector("[data-report-form]");

  // Default the date to today.
  form.querySelector('[name="occurred_on"]').value = new Date().toISOString().slice(0, 10);

  async function fillSelect(name, loader) {
    try {
      const { results } = await loader();
      const sel = form.querySelector(`[name="${name}"]`);
      const keep = sel.value;
      sel.innerHTML = '<option value="">—</option>';
      for (const r of results) {
        const o = document.createElement("option");
        o.value = r.id;
        o.textContent = r.building ? `${r.name} (${r.building})` : r.name;
        sel.appendChild(o);
      }
      sel.value = keep;
    } catch {
      /* optional fields; reporting still works without them */
    }
  }
  fillSelect("category_id", api.listCategories);
  fillSelect("location_id", api.listLocations);

  document.querySelector("[data-add-location]").addEventListener("click", async () => {
    clearError(form);
    const d = formData(form);
    if (!d.new_location_name) return;
    try {
      const loc = await api.createLocation({
        name: d.new_location_name,
        building: d.new_location_building || null,
      });
      await fillSelect("location_id", api.listLocations);
      form.querySelector('[name="location_id"]').value = loc.id;
      form.querySelector('[name="new_location_name"]').value = "";
      form.querySelector('[name="new_location_building"]').value = "";
    } catch (err) {
      showError(err, form);
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError(form);
    const btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      const d = formData(form);
      const item = await api.createItem({
        name: d.name,
        description: d.description,
        kind: d.kind,
        occurred_on: d.occurred_on,
        category_id: d.category_id ? Number(d.category_id) : null,
        location_id: d.location_id ? Number(d.location_id) : null,
      });
      window.location.href = `/app/item.html?id=${item.id}`;
    } catch (err) {
      showError(err, form);
    } finally {
      btn.disabled = false;
    }
  });
}
