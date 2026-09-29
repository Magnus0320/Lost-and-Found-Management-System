import { api, showError, clearError, formData } from "../api.js";
import { showDevCode } from "../ui.js";

const form = document.querySelector("[data-reset-request-form]");
const devBox = document.querySelector("[data-dev-otp]");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError(form);
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    const email = formData(form).email;
    const data = await api.passwordResetRequest({ email });
    if (data.otp_debug) {
      // Dev only: mail disabled, so the API returns the code directly.
      showDevCode(devBox, data.otp_debug);
      setTimeout(() => {
        const p = new URLSearchParams({ email, otp: data.otp_debug });
        window.location.href = `/app/reset-confirm.html?${p}`;
      }, 1200);
    } else {
      const p = new URLSearchParams({ email });
      window.location.href = `/app/reset-confirm.html?${p}`;
    }
  } catch (err) {
    showError(err, form);
  } finally {
    btn.disabled = false;
  }
});
