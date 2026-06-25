import { loadCases, casePageUrl } from "./app.js";

const surpriseButton = document.getElementById("surprise-me");

async function init() {
  if (!surpriseButton) {
    return;
  }

  surpriseButton.addEventListener("click", async () => {
    try {
      const cases = await loadCases();
      if (cases.length === 0) {
        return;
      }
      const pick = cases[Math.floor(Math.random() * cases.length)];
      window.location.href = casePageUrl(pick.id);
    } catch (error) {
      surpriseButton.disabled = true;
      surpriseButton.textContent = "Cases unavailable offline";
      console.error(error);
    }
  });
}

init();
