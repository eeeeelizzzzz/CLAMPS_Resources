import {
  loadDeployments,
  sortDeployments,
  renderDeploymentTableBody,
  saveDeploymentSort,
  loadDeploymentSort,
} from "./deployments.js";

const table = document.querySelector(".deployment-table");
const tableBody = document.getElementById("deployment-table-body");
const tableHead = table?.querySelector("thead");

let allDeployments = [];
let currentSort = loadDeploymentSort();

function navigateToDeployment(row) {
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
      navigateToDeployment(row);
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        navigateToDeployment(row);
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
  const sorted = sortDeployments(
    allDeployments,
    currentSort.column,
    currentSort.direction
  );
  tableBody.innerHTML = renderDeploymentTableBody(sorted);
  bindTableRows();
  updateSortIndicators();
  saveDeploymentSort(currentSort);
}

function handleSortClick(event) {
  const button = event.target.closest(".case-table__sort");
  if (!button) {
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

  try {
    allDeployments = await loadDeployments();
    renderTable();
  } catch (error) {
    tableBody.innerHTML = `<tr><td colspan="4" class="error-state">${error.message}</td></tr>`;
  }
}

init();
