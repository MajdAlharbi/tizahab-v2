const AUTH_I18N = {
  en: {
    login: "Login",
    createAccount: "Create Account",
    emailAddress: "Email Address",
    password: "Password",
    forgotPassword: "Forgot password?",
    loading: "Loading...",
    orContinue: "Or continue with",
    continueGoogle: "Continue with Google",
    continueFacebook: "Continue with Facebook",
    continueGuest: "Continue as Guest",
    backHome: "Back to Home",
    fullName: "Full Name",
    confirmPassword: "Confirm Password",
    passwordHelp: "Password must be at least 8 characters",
    passwordMismatch: "Passwords do not match",
    forgotTitle: "Forgot password?",
    forgotIntro: "Enter the email associated with your account and we'll send an email with instructions to reset your password.",
    enterEmail: "Enter Email Address",
    sendReset: "Send Reset Link",
    sending: "Sending...",
    backLogin: "Back to Login",
    resetTitle: "Create a new password",
    newPassword: "New Password",
    retypePassword: "Retype password",
    resetPassword: "Reset Password",
    namePlaceholder: "Enter your name",
    emailPlaceholder: "your@email.com",
    passwordPlaceholder: "Enter your password",
    confirmPlaceholder: "Re-enter your password",
    retypePlaceholder: "Retype password",
  },
  ar: {
    login: "تسجيل الدخول",
    createAccount: "إنشاء حساب",
    emailAddress: "البريد الإلكتروني",
    password: "كلمة المرور",
    forgotPassword: "نسيت كلمة المرور؟",
    loading: "جاري التحميل...",
    orContinue: "أو المتابعة باستخدام",
    continueGoogle: "المتابعة عبر Google",
    continueFacebook: "المتابعة عبر Facebook",
    continueGuest: "المتابعة كزائر",
    backHome: "العودة للرئيسية",
    fullName: "الاسم الكامل",
    confirmPassword: "تأكيد كلمة المرور",
    passwordHelp: "يجب أن تكون كلمة المرور 8 أحرف على الأقل",
    passwordMismatch: "كلمتا المرور غير متطابقتين",
    forgotTitle: "نسيت كلمة المرور؟",
    forgotIntro: "أدخل البريد الإلكتروني المرتبط بحسابك، وسنرسل لك رابطاً لإعادة تعيين كلمة المرور.",
    enterEmail: "أدخل البريد الإلكتروني",
    sendReset: "إرسال رابط الاستعادة",
    sending: "جاري الإرسال...",
    backLogin: "العودة لتسجيل الدخول",
    resetTitle: "إنشاء كلمة مرور جديدة",
    newPassword: "كلمة المرور الجديدة",
    retypePassword: "تأكيد كلمة المرور",
    resetPassword: "تغيير كلمة المرور",
    namePlaceholder: "أدخل اسمك",
    emailPlaceholder: "your@email.com",
    passwordPlaceholder: "أدخل كلمة المرور",
    confirmPlaceholder: "أعد إدخال كلمة المرور",
    retypePlaceholder: "أعد إدخال كلمة المرور",
  },
};

function getAuthLang() {
  return document.documentElement.lang === "ar" ? "ar" : "en";
}

function applyAuthLanguage(lang = getAuthLang()) {
  const safeLang = lang === "ar" ? "ar" : "en";
  const dict = AUTH_I18N[safeLang];

  localStorage.setItem("tz_lang", safeLang);
  localStorage.setItem("language", safeLang);
  document.documentElement.setAttribute("lang", safeLang);
  document.documentElement.setAttribute("dir", safeLang === "ar" ? "rtl" : "ltr");

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (dict[key]) el.textContent = dict[key];
  });

  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    if (dict[key]) el.setAttribute("placeholder", dict[key]);
  });

  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const key = el.dataset.i18nTitle;
    if (dict[key]) el.setAttribute("title", dict[key]);
  });

  document.querySelectorAll(".lang-btn").forEach((btn) => {
    const active = btn.dataset.lang === safeLang;
    btn.classList.toggle("bg-violet-600", active);
    btn.classList.toggle("text-white", active);
    btn.classList.toggle("text-gray-600", !active);
    btn.classList.toggle("hover:bg-gray-100", !active);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  applyAuthLanguage(getAuthLang());
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      applyAuthLanguage(btn.dataset.lang);
    }, true);
  });
});

window.applyAuthLanguage = applyAuthLanguage;
window.authT = function authT(key, fallback = "") {
  const lang = getAuthLang();
  return AUTH_I18N[lang]?.[key] || AUTH_I18N.en[key] || fallback || key;
};
