import {
  loadCases,
  formatDate,
  getCaseById,
  getQueryParam,
  renderTags,
  renderFigures,
  renderSections,
} from "./app.js";
import { renderCaseMath } from "./math.js";

const content = document.getElementById("case-content");

async function init() {
  const caseId = getQueryParam("id");

  if (!caseId) {
    content.innerHTML = `
      <div class="error-state">
        <p>No case selected. <a href="case-table.html">Return to the case table</a>.</p>
      </div>
    `;
    return;
  }

  try {
    const cases = await loadCases();
    const entry = getCaseById(cases, caseId);

    if (!entry) {
      content.innerHTML = `
        <div class="error-state">
          <p>Case not found: <strong>${caseId}</strong></p>
          <p><a href="case-table.html">Return to the case table</a></p>
        </div>
      `;
      return;
    }

    document.title = `${entry.title} — CLAMPS Case Gallery`;

    content.innerHTML = `
      <header class="case-header">
        <h1>${entry.title}</h1>
        <div class="case-meta">
          <span>${entry.subtitle}</span>
          <span>${formatDate(entry.date)}</span>
          <span>${entry.campaign}</span>
          <span>${entry.location}</span>
        </div>
        ${renderTags(entry.tags)}
      </header>

      ${renderFigures(entry)}

      ${renderSections(entry.sections)}
    `;
    renderCaseMath(content);
  } catch (error) {
    content.innerHTML = `<div class="error-state">${error.message}</div>`;
  }
}

init();
