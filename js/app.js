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

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderCaseTableRow(entry) {
  const url = casePageUrl(entry.id);

  return `
    <tr
      class="case-table__row"
      tabindex="0"
      role="link"
      data-href="${url}"
      data-date="${escapeHtml(entry.date)}"
      data-platform="${escapeHtml(entry.subtitle)}"
      data-title="${escapeHtml(entry.title)}"
      data-campaign="${escapeHtml(entry.campaign)}"
      data-location="${escapeHtml(entry.location)}"
    >
      <td><a href="${url}">${formatDate(entry.date)}</a></td>
      <td>${escapeHtml(entry.subtitle)}</td>
      <td>${escapeHtml(entry.title)}</td>
      <td>${escapeHtml(entry.campaign)}</td>
      <td>${escapeHtml(entry.location)}</td>
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

function isFourPanelFigure(figure) {
  return figure.src.includes("instrument_template_4panel");
}

function splitCaseFigures(entry) {
  const images = getCaseImages(entry);
  const primary = images.filter(isFourPanelFigure);
  const auxiliary = images.filter((figure) => !isFourPanelFigure(figure));

  if (primary.length === 0 && images.length > 0) {
    return { primary: [images[0]], auxiliary: images.slice(1) };
  }

  return { primary, auxiliary };
}

function figureBasename(src) {
  return src.split("/").pop().replace(/\.[^.]+$/, "");
}

function figureAnchorId(src) {
  return `figure-${figureBasename(src)}`;
}

function buildFigureRefMap(entry) {
  const map = new Map();

  for (const figure of getCaseImages(entry)) {
    const basename = figureBasename(figure.src).toLowerCase();
    map.set(basename, {
      id: figureAnchorId(figure.src),
      label: figure.label,
    });
  }

  return map;
}

const FIGURE_FILENAME_PATTERN =
  /\b([a-zA-Z0-9][a-zA-Z0-9_.-]+\.(?:png|jpe?g|gif))\b/gi;

const FOUR_PANEL_CAPTION =
  'A four-panel visualization of observations available from the CLAMPS facility. $z_{i}$ is traced on top of all panels using the fuzzy logic algorithm presented in <a href="https://amt.copernicus.org/articles/17/4087/2024/" target="_blank" rel="noopener noreferrer">Smith and Carlin (2024)</a>. (A) Virtual potential temperature and (B) water vapor mixing ratio as retrieved from TROPoe. The base instrumentation used in the retrieval is listed in the panel title(s). Where cloud bases are detected (by the Doppler lidar) and the retrieval has sufficient LWC, clouds are designated by black markers. (C) Horizontal wind profiles from Doppler lidar observations. When WINDoe is used, DL PPI scans are the basis of the retrieval. The gray dashed line shows the level where standard VAD-based wind profiles lose signal. Levels where the WINDoe uncertainty is larger than 2 $m s^{-1}$ show up as fainter colorfill. Wind barbs in those uncertain layers are plotted as black with white outlines. (D) Vertical velocity variance is computed from 1-s vertically pointed stares and has an intensity (i.e., SNR) filter applied to exclude noise.';

function getFigureCaption(figure) {
  if (figure.caption) {
    return figure.caption;
  }

  if (isFourPanelFigure(figure)) {
    return FOUR_PANEL_CAPTION;
  }

  return "";
}

function renderFigureCaption(figure, entry) {
  const caption = getFigureCaption(figure);

  if (!caption) {
    return "";
  }

  const figureRefMap = entry ? buildFigureRefMap(entry) : new Map();
  const linkedCaption = linkifyFigureRefs(caption, figureRefMap);

  return `
    <figcaption class="figure-panel__caption">
      <p>${linkedCaption}</p>
    </figcaption>
  `;
}

function linkifyFigureRefs(text, figureRefMap) {
  if (!text || figureRefMap.size === 0) {
    return text;
  }

  return text.replace(FIGURE_FILENAME_PATTERN, (match) => {
    const basename = match.replace(/\.[^.]+$/, "").toLowerCase();
    const ref = figureRefMap.get(basename);

    if (!ref) {
      return match;
    }

    return `<a href="#${ref.id}" class="figure-ref">${escapeHtml(ref.label)}</a>`;
  });
}

function renderFigurePanel(figure, entry, extraClass = "") {
  const className = extraClass
    ? `figure-panel ${extraClass}`
    : "figure-panel";

  return `
    <figure class="${className}" id="${figureAnchorId(figure.src)}">
      <figcaption class="figure-panel__header">${figure.label}</figcaption>
      <div class="figure-panel__body">
        <img
          src="${figure.src}"
          alt="${entry.title} — ${figure.label}"
        >
      </div>
      ${renderFigureCaption(figure, entry)}
    </figure>
  `;
}

function renderPrimaryFigures(entry) {
  const { primary } = splitCaseFigures(entry);

  if (primary.length === 0) {
    return "";
  }

  return `
    <div class="case-figures case-figures--primary">
      ${primary.map((figure) => renderFigurePanel(figure, entry)).join("")}
    </div>
  `;
}

function renderAuxiliaryFigures(entry) {
  const { auxiliary } = splitCaseFigures(entry);

  if (auxiliary.length === 0) {
    return "";
  }

  return `
    <div class="case-figures case-figures--auxiliary">
      ${auxiliary.map((figure) => renderFigurePanel(figure, entry)).join("")}
    </div>
  `;
}

function renderFigures(entry) {
  const { primary, auxiliary } = splitCaseFigures(entry);
  const figures = [...primary, ...auxiliary];

  return figures.map((figure) => renderFigurePanel(figure, entry)).join("");
}

function renderSections(sections, entry) {
  if (!sections || sections.length === 0) {
    return `
      <section class="content-section placeholder-note">
        <h2>Additional content</h2>
        <p>More case information and visualizations will be added here as they are developed.</p>
      </section>
    `;
  }

  const figureRefMap = entry ? buildFigureRefMap(entry) : new Map();

  return sections
    .map((section) => {
      if (section.type === "html") {
        return `
          <section class="content-section">
            <h2>${section.title}</h2>
            ${linkifyFigureRefs(section.content, figureRefMap)}
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
          .map((item) => `<li>${linkifyFigureRefs(item, figureRefMap)}</li>`)
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
          <p>${linkifyFigureRefs(section.content, figureRefMap)}</p>
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
  renderPrimaryFigures,
  renderAuxiliaryFigures,
  renderSections,
};
