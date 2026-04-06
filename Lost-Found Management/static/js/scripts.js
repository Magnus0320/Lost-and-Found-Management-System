function validateEmail() {
    const emailField = document.getElementById('email');
    const emailError = document.getElementById('emailError');
    const collegeDomain = '@nitt.edu';

    if (!emailField.value.endsWith(collegeDomain)) {
        emailError.textContent = 'Please enter a valid college email address (e.g., yourrollno@nitt.edu).';
        return false;
    } else {
        emailError.textContent = ''; //enter eeror message
    }

    return validatePassword();
}

function validatePassword() {
    const passwordField = document.getElementById('password');
    const confirmPasswordField = document.getElementById('confirm_password');
    const passwordError = document.getElementById('passwordError');

    if (passwordField.value !== confirmPasswordField.value) {
        passwordError.textContent = 'Passwords do not match.';
        return false;
    } else {
        passwordError.textContent = ''; // Clear any previous error message
    }

    return true;
}
