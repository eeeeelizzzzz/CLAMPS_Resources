const DEPLOYMENTS_URL = new URL("../data/deployments.json", import.meta.url).href;

let deploymentsCache = null;

async function loadDeployments() {
  if (deploymentsCache) return deploymentsCache;

  if (window.location.protocol === "file:") {
    throw new Error(
      "Deployments cannot load from a local file. Use a web server (python3 -m http.server) or open the GitHub Pages site."
    );
  }

  const response = await fetch(DEPLOYMENTS_URL);
  if (!response.ok) {
    throw new Error(`Failed to load deployments (${response.status})`);
  }

  deploymentsCache = await response.json();
  return deploymentsCache;
}

function formatDateRange(startDate, endDate) {
  const start = formatDeploymentDate(startDate);
  const end = formatDeploymentDate(endDate);
  const [sy] = startDate.split("-");
  const [ey] = endDate.split("-");
  if (sy === ey && startDate.slice(0, 7) === endDate.slice(0, 7)) {
    return start;
  }
  if (sy === ey) {
    return `${start} – ${end}`;
  }
  return `${start} – ${end}`;
}

function formatDeploymentDate(isoDate) {
  const [year, month] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, 1));
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    timeZone: "UTC",
  });
}

function deploymentPageUrl(id) {
  return `deployment.html?id=${encodeURIComponent(id)}`;
}

const DEPLOYMENT_SORT_STORAGE_KEY = "clampsResources.deploymentSort";
const DEFAULT_DEPLOYMENT_SORT = { column: "date", direction: "asc" };

const DEPLOYMENT_SORT_COLUMNS = {
  date: (entry) => entry.start_date,
  location: (entry) => entry.location,
  platform: (entry) => entry.platform,
  campaign: (entry) => entry.campaign,
};

function sortDeployments(deployments, column, direction) {
  const getValue = DEPLOYMENT_SORT_COLUMNS[column];
  if (!getValue) return [...deployments];

  const factor = direction === "desc" ? -1 : 1;

  return [...deployments].sort((a, b) => {
    const compare = getValue(a).localeCompare(getValue(b), undefined, {
      sensitivity: "base",
    });
    if (compare !== 0) return compare * factor;
    return a.id.localeCompare(b.id) * factor;
  });
}

function loadDeploymentSort() {
  try {
    const raw = sessionStorage.getItem(DEPLOYMENT_SORT_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_DEPLOYMENT_SORT };

    const parsed = JSON.parse(raw);
    if (
      DEPLOYMENT_SORT_COLUMNS[parsed.column] &&
      (parsed.direction === "asc" || parsed.direction === "desc")
    ) {
      return parsed;
    }
  } catch {
    // Ignore invalid stored sort state.
  }

  return { ...DEFAULT_DEPLOYMENT_SORT };
}

function saveDeploymentSort(sort) {
  sessionStorage.setItem(DEPLOYMENT_SORT_STORAGE_KEY, JSON.stringify(sort));
}

function getDeploymentById(deployments, id) {
  return deployments.find((entry) => entry.id === id);
}

function getDeploymentNeighbors(deployments, deploymentId, sort = loadDeploymentSort()) {
  const sorted = sortDeployments(deployments, sort.column, sort.direction);
  const index = sorted.findIndex((entry) => entry.id === deploymentId);

  if (index === -1) {
    return { prev: null, next: null };
  }

  return {
    prev: index > 0 ? sorted[index - 1] : null,
    next: index < sorted.length - 1 ? sorted[index + 1] : null,
  };
}

function deploymentNavMeta(entry) {
  const period = entry.period || formatDateRange(entry.start_date, entry.end_date);
  return `${period} · ${entry.platform}`;
}

function renderDeploymentNavLink(entry, direction) {
  const isPrev = direction === "prev";
  const arrow = isPrev ? "←" : "→";
  const label = isPrev ? "Previous deployment" : "Next deployment";

  return `
    <a
      class="case-nav__link case-nav__link--${direction}"
      href="${deploymentPageUrl(entry.id)}"
    >
      <span class="case-nav__direction">${isPrev ? `${arrow} ${label}` : `${label} ${arrow}`}</span>
      <span class="case-nav__title">${escapeHtml(entry.campaign)}</span>
      <span class="case-nav__meta">${escapeHtml(deploymentNavMeta(entry))}</span>
    </a>
  `;
}

function renderDeploymentNav(prev, next) {
  if (!prev && !next) {
    return "";
  }

  const prevHtml = prev
    ? renderDeploymentNavLink(prev, "prev")
    : `<span class="case-nav__spacer" aria-hidden="true"></span>`;
  const nextHtml = next
    ? renderDeploymentNavLink(next, "next")
    : `<span class="case-nav__spacer" aria-hidden="true"></span>`;

  return `
    <nav class="case-nav" aria-label="Deployment navigation">
      ${prevHtml}
      ${nextHtml}
    </nav>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderDeploymentTableRow(entry) {
  const url = deploymentPageUrl(entry.id);
  const dateLabel = entry.period || formatDateRange(entry.start_date, entry.end_date);

  return `
    <tr
      class="case-table__row"
      tabindex="0"
      role="link"
      data-href="${url}"
      data-date="${escapeHtml(entry.start_date)}"
      data-location="${escapeHtml(entry.location)}"
      data-platform="${escapeHtml(entry.platform)}"
      data-campaign="${escapeHtml(entry.campaign)}"
    >
      <td><a href="${url}">${dateLabel}</a></td>
      <td>${escapeHtml(entry.location)}</td>
      <td>${escapeHtml(entry.platform)}</td>
      <td>${escapeHtml(entry.campaign)}</td>
    </tr>
  `;
}

function renderDeploymentTableBody(deployments) {
  if (deployments.length === 0) {
    return `
      <tr>
        <td colspan="4" class="empty-state">No deployments available.</td>
      </tr>
    `;
  }

  return deployments.map(renderDeploymentTableRow).join("");
}

function renderDeploymentReferences(references) {
  if (!references || references.length === 0) {
    return "";
  }

  const items = references
    .map(
      (ref) =>
        `<li><a href="${escapeHtml(ref.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(ref.label)}</a></li>`
    )
    .join("");

  return `
    <section class="content-section">
      <h2>References</h2>
      <ul>${items}</ul>
    </section>
  `;
}

function renderDeploymentWebsites(websites) {
  if (!websites || websites.length === 0) {
    return "";
  }

  const items = websites
    .map(
      (site) =>
        `<li><a href="${escapeHtml(site.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(site.label)}</a></li>`
    )
    .join("");

  return `
    <section class="content-section">
      <h2>Related websites</h2>
      <ul>${items}</ul>
    </section>
  `;
}

function renderDeploymentPhotos(photos) {
  if (!photos || photos.length === 0) {
    return "";
  }

  const figures = photos
    .map(
      (photo) => `
        <figure class="deployment-photo">
          <div class="deployment-photo__body">
            <img src="${escapeHtml(photo.src)}" alt="" loading="lazy">
          </div>
          <figcaption>${photo.caption}</figcaption>
        </figure>
      `
    )
    .join("");

  return `
    <section class="content-section">
      <h2>Photos</h2>
      <div class="deployment-photos">${figures}</div>
    </section>
  `;
}

function renderDeploymentSubprojects(subprojects) {
  if (!subprojects || subprojects.length === 0) {
    return "";
  }

  const rows = subprojects
    .map(
      (sub) => `
        <tr>
          <td>${escapeHtml(sub.name)}</td>
          <td>${escapeHtml(sub.platform)}</td>
          <td>${escapeHtml(sub.period)}</td>
          <td>${escapeHtml(sub.location)}</td>
          <td>${escapeHtml(sub.notes || "")}</td>
        </tr>
      `
    )
    .join("");

  return `
    <section class="content-section">
      <h2>Deployment stints</h2>
      <div class="table-panel">
        <table class="case-table deployment-subprojects" aria-label="Deployment stints">
          <thead>
            <tr>
              <th scope="col">Project</th>
              <th scope="col">CLAMPS</th>
              <th scope="col">Period</th>
              <th scope="col">Location</th>
              <th scope="col">Notes</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
  `;
}

export {
  loadDeployments,
  formatDateRange,
  formatDeploymentDate,
  deploymentPageUrl,
  loadDeploymentSort,
  saveDeploymentSort,
  sortDeployments,
  getDeploymentById,
  getDeploymentNeighbors,
  renderDeploymentNav,
  renderDeploymentTableBody,
  renderDeploymentReferences,
  renderDeploymentWebsites,
  renderDeploymentPhotos,
  renderDeploymentSubprojects,
};
