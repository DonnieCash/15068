/* NK15068 — run this page's module (the page id is <html data-page>) */
(function () {
  "use strict";
  const page = document.documentElement.dataset.page;
  const run = window.NKS && window.NKS.pages[page];
  if (!run) return;
  try {
    const r = run();
    if (r && typeof r.catch === "function") r.catch((e) => console.error(e));
  } catch (e) {
    console.error(e);
  }
})();
