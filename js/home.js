import { loadCases, sortTableCases, renderCaseTableBody, saveTableSort, loadTableSort } from "./app.js";

const table = document.querySelector(".case-table");
const tableBody = document.getElementById("case-table-body");
const tableHead = table?.querySelector("thead");

let allCases = [];
let currentSort = loadTableSort();

function getCaseIdFromRow(row) {
  const href = row.dataset.href;
  if (!href) return "";
  return new URL(href, window.location.href).searchParams.get("id") || "";
}

function casesFromTableRows() {
  return [...tableBody.querySelectorAll(".case-table__row")].map((row) => ({
    id: getCaseIdFromRow(row),
    date: row.dataset.date || "",
    subtitle: row.dataset.platform || "",
    title: row.dataset.title || "",
    campaign: row.dataset.campaign || "",
    location: row.dataset.location || "",
  }));
}

function navigateToCase(row) {
  const href = row.dataset.href;
  if (href) {
    window.location.href = href;
  }
}

function bindTableRows() {
  tableBody.querySelectorAll(".case-table__row").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("a")) {
        return;
      }
      navigateToCase(row);
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        navigateToCase(row);
      }
    });
  });
}

function updateSortIndicators() {
  tableHead?.querySelectorAll(".case-table__sort").forEach((button) => {
    const column = button.dataset.column;
    const indicator = button.querySelector(".case-table__sort-indicator");

    if (column === currentSort.column) {
      button.setAttribute(
        "aria-sort",
        currentSort.direction === "asc" ? "ascending" : "descending"
      );
      indicator.textContent = currentSort.direction === "asc" ? "▲" : "▼";
      button.classList.add("case-table__sort--active");
    } else {
      button.setAttribute("aria-sort", "none");
      indicator.textContent = "";
      button.classList.remove("case-table__sort--active");
    }
  });
}

function renderTable() {
  if (allCases.length === 0) {
    return;
  }

  const sorted = sortTableCases(
    allCases,
    currentSort.column,
    currentSort.direction
  );
  tableBody.innerHTML = renderCaseTableBody(sorted);
  bindTableRows();
  updateSortIndicators();
  saveTableSort(currentSort);
}

function handleSortClick(event) {
  const button = event.target.closest(".case-table__sort");
  if (!button || allCases.length === 0) {
    return;
  }

  event.preventDefault();

  const column = button.dataset.column;
  if (!column) {
    return;
  }

  if (currentSort.column === column) {
    currentSort.direction = currentSort.direction === "asc" ? "desc" : "asc";
  } else {
    currentSort = { column, direction: "asc" };
  }

  renderTable();
}

async function init() {
  if (!tableBody || !tableHead) {
    return;
  }

  tableHead.addEventListener("click", handleSortClick);
  bindTableRows();
  allCases = casesFromTableRows();

  try {
    const fetched = await loadCases();
    if (fetched.length > 0) {
      allCases = fetched;
      renderTable();
      return;
    }
  } catch {
    // Keep cases parsed from the static table rows.
  }

  saveTableSort(currentSort);
  updateSortIndicators();
}

init();
