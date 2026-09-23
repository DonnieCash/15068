/* NK15068 — crime pages: /crime/, /crime/<town>/, /crime/blotter/, /crashes/.
   Everything is in the HTML; JS adds chart readouts, puts my town's short answer first, and runs the blotter filters. */
(function () {
  "use strict";
  const NKS = window.NKS;
  if (!NKS) return;
  const S = () => window.NKSafety;

  /* /crime/: my town's short answer first (reorders, never hides) */
  function orderAnswers() {
    const box = NKS.$("#answers");
    if (!box) return;
    const items = NKS.$$(".ans[data-town]", box);
    const ordered = NKS.townFirst(NKS.TOWNS, (t) => t);
    ordered.forEach((t) => { const el = items.find((x) => x.dataset.town === t); if (el) box.appendChild(el); });
    items.forEach((el) => el.classList.toggle("mine", el.dataset.town === NKS.town()));
  }

  NKS.pages.crime = () => {
    if (S()) S().enhanceCharts(document);
    orderAnswers();
    document.addEventListener("nk-town", orderAnswers);
  };
  NKS.pages["crime-dept"] = () => { if (S()) S().enhanceCharts(document); };
  NKS.pages.crashes = () => { if (S()) S().enhanceCharts(document); };
  NKS.pages.blotter = () => { if (S()) S().enhanceBlotter(NKS.$("#inc-block")); };
})();
