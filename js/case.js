import {
  loadCases,
  formatDate,
  getCaseById,
  getQueryParam,
  getCaseNeighbors,
  renderTags,
  renderPrimaryFigures,
  renderAuxiliaryFigures,
  renderSections,
  renderCaseNav,
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

    const { prev, next } = getCaseNeighbors(cases, caseId);

    content.innerHTML = `
      ${renderCaseNav(prev, next)}

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

      ${renderPrimaryFigures(entry)}

      ${renderSections(entry.sections, entry)}

      ${renderAuxiliaryFigures(entry)}

      ${renderCaseNav(prev, next)}
    `;
    renderCaseMath(content);
  } catch (error) {
    content.innerHTML = `<div class="error-state">${error.message}</div>`;
  }
}

init();
