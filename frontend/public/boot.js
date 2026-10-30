// Before first paint: language and theme, so the page never flashes the wrong one.
(function () {
  var lang = "ar";
  var theme = "system";
  try {
    lang = localStorage.getItem("sabq.lang") === "fr" ? "fr" : "ar";
    theme = localStorage.getItem("sabq.theme") || "system";
  } catch (e) {}
  var root = document.documentElement;
  root.lang = lang;
  root.dir = lang === "ar" ? "rtl" : "ltr";
  if (theme === "system") {
    theme = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  root.dataset.theme = theme;
})();
