import renderMathInElement from "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.mjs";

const MATH_OPTIONS = {
  delimiters: [
    { left: "$$", right: "$$", display: true },
    { left: "$", right: "$", display: false },
  ],
  throwOnError: false,
};

export function renderCaseMath(root) {
  if (!root) {
    return;
  }

  renderMathInElement(root, MATH_OPTIONS);
}
