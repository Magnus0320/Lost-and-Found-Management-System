import { api, showError, clearError, formData } from "../api.js";

const form = document.querySelector("[data-register-form]");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError(form);
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    const payload = formData(form);
    payload.batch = Number(payload.batch);
    const data = await api.register(payload);
    // The API returns otp_debug only when outbound mail is disabled (dev).
    const params = new URLSearchParams({ email: payload.email });
    if (data.otp_debug) params.set("otp", data.otp_debug);
    window.location.href = `/app/verify.html?${params}`;
  } catch (err) {
    showError(err, form);
  } finally {
    btn.disabled = false;
  }
});
