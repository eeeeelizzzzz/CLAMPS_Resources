import {
  loadDeployments,
  formatDateRange,
  getDeploymentById,
  getDeploymentNeighbors,
  renderDeploymentNav,
  renderDeploymentReferences,
  renderDeploymentWebsites,
  renderDeploymentPhotos,
  renderDeploymentSubprojects,
} from "./deployments.js";

const content = document.getElementById("deployment-content");

function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

async function init() {
  const deploymentId = getQueryParam("id");

  if (!deploymentId) {
    content.innerHTML = `
      <div class="error-state">
        <p>No deployment selected. <a href="deployments.html">Return to deployment history</a>.</p>
      </div>
    `;
    return;
  }

  try {
    const deployments = await loadDeployments();
    const entry = getDeploymentById(deployments, deploymentId);

    if (!entry) {
      content.innerHTML = `
        <div class="error-state">
          <p>Deployment not found: <strong>${deploymentId}</strong></p>
          <p><a href="deployments.html">Return to deployment history</a></p>
        </div>
      `;
      return;
    }

    document.title = `${entry.campaign} — CLAMPS Deployment History`;

    const { prev, next } = getDeploymentNeighbors(deployments, deploymentId);

    const fullNameHtml = entry.full_name
      ? `<p class="deployment-full-name">${entry.full_name}</p>`
      : "";

    const periodLabel = entry.period || formatDateRange(entry.start_date, entry.end_date);

    const notesHtml = entry.notes
      ? `
        <section class="content-section">
          <h2>Deployment notes</h2>
          <p>${entry.notes}</p>
        </section>
      `
      : "";

    content.innerHTML = `
      ${renderDeploymentNav(prev, next)}

      <header class="case-header">
        <h1>${entry.campaign}</h1>
        ${fullNameHtml}
        <div class="case-meta">
          <span>${entry.platform}</span>
          <span>${periodLabel}</span>
          <span>${entry.location}</span>
        </div>
      </header>

      <section class="content-section">
        <h2>Summary</h2>
        <p>${entry.summary}</p>
      </section>

      ${notesHtml}

      ${renderDeploymentSubprojects(entry.subprojects)}

      ${renderDeploymentPhotos(entry.photos)}

      ${renderDeploymentReferences(entry.references)}

      ${renderDeploymentWebsites(entry.websites)}

      ${renderDeploymentNav(prev, next)}

      <p class="page-actions">
        <a href="deployments.html" class="doc-button">← Back to deployment history</a>
      </p>
    `;
  } catch (error) {
    content.innerHTML = `<div class="error-state">${error.message}</div>`;
  }
}

init();
