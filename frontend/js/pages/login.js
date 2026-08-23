import { api, auth, showError, clearError, showNotice, formData, qs } from "../api.js";

const form = document.querySelector("[data-login-form]");

// Carry over a message from registration/verification/reset.
const flash = qs("msg");
if (flash) showNotice(flash, "ok");
const prefill = qs("email");
if (prefill) form.querySelector('[name="email"]').value = prefill;

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError(form);
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    const data = await api.login(formData(form));
    auth.save(data.access_token, data.user);
    const next = qs("next");
    window.location.href = next && next.startsWith("/app/") ? next : "/app/index.html";
  } catch (err) {
    // 401 here means bad credentials, not an expired session -- show it inline
    // rather than letting the global handler bounce us to this same page.
    showError(err, form);
  } finally {
    btn.disabled = false;
  }
});
