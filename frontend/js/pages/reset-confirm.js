import { api, showError, clearError, formData, qs } from "../api.js";

const form = document.querySelector("[data-reset-confirm-form]");
for (const f of ["email", "otp"]) {
  const v = qs(f);
  if (v) form.querySelector(`[name="${f}"]`).value = v;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError(form);
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    const payload = formData(form);
    await api.passwordResetConfirm(payload);
    const p = new URLSearchParams({
      email: payload.email,
      msg: "Password updated. Log in with your new password.",
    });
    window.location.href = `/app/login.html?${p}`;
  } catch (err) {
    showError(err, form);
  } finally {
    btn.disabled = false;
  }
});
