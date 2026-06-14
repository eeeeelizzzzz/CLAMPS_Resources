const CASES_URL = new URL("../data/cases.json", import.meta.url).href;

let casesCache = null;

async function loadCases() {
  if (casesCache) return casesCache;

  if (window.location.protocol === "file:") {
    throw new Error(
      "Cases cannot load from a local file. Use a web server (python3 -m http.server) or open the GitHub Pages site."
    );
  }

  const response = await fetch(CASES_URL);
  if (!response.ok) {
    throw new Error(`Failed to load cases (${response.status})`);
  }

  casesCache = await response.json();
  return casesCache;
}

function formatDate(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

const CASE_ALIASES = {
  ci_c1: "ci_gravity_waves_c1",
  gravity_waves_c1: "ci_gravity_waves_c1",
  sea_breeze_c1: "sea_breeze",
  sea_breeze_c2: "sea_breeze",
};

const TABLE_SORT_STORAGE_KEY = "clampsCaseGallery.tableSort";
const DEFAULT_TABLE_SORT = { column: "date", direction: "asc" };

function resolveCaseId(id) {
  return CASE_ALIASES[id] || id;
}

function getCaseById(cases, id) {
  const resolvedId = resolveCaseId(id);
  return cases.find((entry) => entry.id === resolvedId);
}

function getPrimaryImage(entry) {
  if (entry.images && entry.images.length > 0) {
    return entry.images[0].src;
  }

  return entry.image;
}

function getCaseImages(entry) {
  if (entry.images && entry.images.length > 0) {
    return entry.images;
  }

  if (entry.image) {
    return [{ src: entry.image, label: "Standard CLAMPS observations" }];
  }

  return [];
}

function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function casePageUrl(id) {
  return `case.html?id=${encodeURIComponent(id)}`;
}

function sortCases(cases, sortBy) {
  const sorted = [...cases];

  if (sortBy === "date-desc") {
    return sorted.sort((a, b) => b.date.localeCompare(a.date));
  }
  if (sortBy === "date-asc") {
    return sorted.sort((a, b) => a.date.localeCompare(b.date));
  }
  if (sortBy === "title") {
    return sorted.sort((a, b) => {
      const titleCompare = a.title.localeCompare(b.title);
      if (titleCompare !== 0) return titleCompare;
      return a.subtitle.localeCompare(b.subtitle);
    });
  }

  return sorted;
}

const TABLE_SORT_COLUMNS = {
  date: (entry) => entry.date,
  platform: (entry) => entry.subtitle,
  title: (entry) => entry.title,
  campaign: (entry) => entry.campaign,
  location: (entry) => entry.location,
};

function sortTableCases(cases, column, direction) {
  const getValue = TABLE_SORT_COLUMNS[column];
  if (!getValue) return [...cases];

  const factor = direction === "desc" ? -1 : 1;

  return [...cases].sort((a, b) => {
    const compare = getValue(a).localeCompare(getValue(b), undefined, {
      sensitivity: "base",
    });
    if (compare !== 0) return compare * factor;
    return a.id.localeCompare(b.id) * factor;
  });
}

function loadTableSort() {
  try {
    const raw = sessionStorage.getItem(TABLE_SORT_STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_TABLE_SORT };
    }

    const parsed = JSON.parse(raw);
    if (
      TABLE_SORT_COLUMNS[parsed.column] &&
      (parsed.direction === "asc" || parsed.direction === "desc")
    ) {
      return parsed;
    }
  } catch {
    // Ignore invalid stored sort state.
  }

  return { ...DEFAULT_TABLE_SORT };
}

function saveTableSort(sort) {
  sessionStorage.setItem(TABLE_SORT_STORAGE_KEY, JSON.stringify(sort));
}

function getCaseNeighbors(cases, caseId, sort = loadTableSort()) {
  const sorted = sortTableCases(cases, sort.column, sort.direction);
  const resolvedId = resolveCaseId(caseId);
  const index = sorted.findIndex((entry) => entry.id === resolvedId);

  if (index === -1) {
    return { prev: null, next: null };
  }

  return {
    prev: index > 0 ? sorted[index - 1] : null,
    next: index < sorted.length - 1 ? sorted[index + 1] : null,
  };
}

function filterCases(cases, query) {
  const needle = query.trim().toLowerCase();
  if (!needle) return cases;

  return cases.filter((entry) => {
    const haystack = [
      entry.id,
      entry.title,
      entry.subtitle,
      entry.date,
      entry.campaign,
      entry.location,
      ...(entry.tags || []),
    ]
      .join(" ")
      .toLowerCase();

    return haystack.includes(needle);
  });
}

function renderTags(tags, extraClass = "") {
  if (!tags || tags.length === 0) return "";

  const className = extraClass ? `tag ${extraClass}` : "tag";
  const items = tags.map((tag) => `<li class="${className}">${tag}</li>`).join("");
  return `<ul class="tag-list">${items}</ul>`;
}

function renderCardTags(entry) {
  const metaTags = [entry.campaign, entry.location].filter(Boolean);
  const metaHtml = metaTags.length
    ? renderTags(metaTags, "tag--meta")
    : "";
  const themeHtml = renderTags(entry.tags);

  if (!metaHtml && !themeHtml) return "";
  return `${metaHtml}${themeHtml}`;
}

function renderCaseTableRow(entry) {
  const url = casePageUrl(entry.id);
  const title = entry.title.replace(/"/g, "&quot;");

  return `
    <tr
      class="case-table__row"
      tabindex="0"
      role="link"
      data-href="${url}"
      data-date="${entry.date}"
      data-platform="${entry.subtitle}"
      data-title="${title}"
      data-campaign="${entry.campaign}"
      data-location="${entry.location}"
    >
      <td><a href="${url}">${formatDate(entry.date)}</a></td>
      <td>${entry.subtitle}</td>
      <td>${entry.title}</td>
      <td>${entry.campaign}</td>
      <td>${entry.location}</td>
    </tr>
  `;
}

function renderCaseTableBody(cases) {
  if (cases.length === 0) {
    return `
      <tr>
        <td colspan="5" class="empty-state">No cases available.</td>
      </tr>
    `;
  }

  return cases.map(renderCaseTableRow).join("");
}

function renderCaseNavLink(entry, direction) {
  const isPrev = direction === "prev";
  const arrow = isPrev ? "←" : "→";
  const label = isPrev ? "Previous case" : "Next case";

  return `
    <a
      class="case-nav__link case-nav__link--${direction}"
      href="${casePageUrl(entry.id)}"
    >
      <span class="case-nav__direction">${isPrev ? `${arrow} ${label}` : `${label} ${arrow}`}</span>
      <span class="case-nav__title">${entry.title}</span>
      <span class="case-nav__meta">${formatDate(entry.date)} · ${entry.subtitle}</span>
    </a>
  `;
}

function renderCaseNav(prev, next) {
  if (!prev && !next) {
    return "";
  }

  const prevHtml = prev
    ? renderCaseNavLink(prev, "prev")
    : `<span class="case-nav__spacer" aria-hidden="true"></span>`;
  const nextHtml = next
    ? renderCaseNavLink(next, "next")
    : `<span class="case-nav__spacer" aria-hidden="true"></span>`;

  return `
    <nav class="case-nav" aria-label="Case navigation">
      ${prevHtml}
      ${nextHtml}
    </nav>
  `;
}

function renderCaseCard(entry) {
  const alt = `${entry.title} — ${entry.subtitle} (${entry.date})`;
  const thumb = getPrimaryImage(entry);

  return `
    <li class="case-card">
      <a href="${casePageUrl(entry.id)}">
        <div class="case-card__thumb">
          <img src="${thumb}" alt="${alt}" loading="lazy">
        </div>
        <div class="case-card__body">
          <p class="case-card__date">${formatDate(entry.date)}</p>
          <h2 class="case-card__title">${entry.title}</h2>
          <p class="case-card__subtitle">${entry.subtitle}</p>
          ${renderCardTags(entry)}
        </div>
      </a>
    </li>
  `;
}

function renderFigures(entry) {
  const images = getCaseImages(entry);

  return images
    .map(
      (figure) => `
        <figure class="figure-panel">
          <figcaption class="figure-panel__header">${figure.label}</figcaption>
          <div class="figure-panel__body">
            <img
              src="${figure.src}"
              alt="${entry.title} — ${figure.label}"
            >
          </div>
        </figure>
      `
    )
    .join("");
}

function renderSections(sections) {
  if (!sections || sections.length === 0) {
    return `
      <section class="content-section placeholder-note">
        <h2>Additional content</h2>
        <p>More case information and visualizations will be added here as they are developed.</p>
      </section>
    `;
  }

  return sections
    .map((section) => {
      if (section.type === "html") {
        return `
          <section class="content-section">
            <h2>${section.title}</h2>
            ${section.content}
          </section>
        `;
      }

      if (section.type === "image") {
        return `
          <section class="content-section">
            <h2>${section.title}</h2>
            <img src="${section.src}" alt="${section.alt || section.title}" loading="lazy">
          </section>
        `;
      }

      if (section.type === "list") {
        const items = (section.items || [])
          .map((item) => `<li>${item}</li>`)
          .join("");

        return `
          <section class="content-section">
            <h2>${section.title}</h2>
            <ul>${items}</ul>
          </section>
        `;
      }

      return `
        <section class="content-section">
          <h2>${section.title}</h2>
          <p>${section.content}</p>
        </section>
      `;
    })
    .join("");
}

export {
  loadCases,
  formatDate,
  getCaseById,
  getQueryParam,
  resolveCaseId,
  casePageUrl,
  loadTableSort,
  saveTableSort,
  getCaseNeighbors,
  sortCases,
  sortTableCases,
  filterCases,
  renderCaseTableBody,
  renderCaseCard,
  renderCardTags,
  renderTags,
  renderCaseNav,
  renderFigures,
  renderSections,
};
