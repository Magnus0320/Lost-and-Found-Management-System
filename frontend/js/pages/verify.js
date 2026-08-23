import { api, showError, clearError, formData, qs } from "../api.js";

const form = document.querySelector("[data-verify-form]");
const devBox = document.querySelector("[data-dev-otp]");

const email = qs("email");
if (email) form.querySelector('[name="email"]').value = email;

// In dev (MAIL_ENABLED=false) the API hands back the code instead of emailing
// it, so the flow is completable without an SMTP server.
const devOtp = qs("otp");
if (devOtp) {
  form.querySelector('[name="otp"]').value = devOtp;
  devBox.innerHTML =
    `Development mode: no email was sent. Your code is <code data-testid="dev-otp-value">${devOtp}</code>`;
  devBox.hidden = false;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError(form);
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    const user = await api.verifyRegistration(formData(form));
    const params = new URLSearchParams({
      email: user.email,
      msg: "Email verified. You can log in now.",
    });
    window.location.href = `/app/login.html?${params}`;
  } catch (err) {
    showError(err, form);
  } finally {
    btn.disabled = false;
  }
});
