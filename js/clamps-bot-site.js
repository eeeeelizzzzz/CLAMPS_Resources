import { renderClampsBotAside, renderClampsBotFooter } from "./outreach.js";

function imagePrefix() {
  const path = window.location.pathname;
  if (path.includes("/bibliometrics/") || path.includes("/case_reproduce/")) {
    return "../";
  }
  return "";
}

function injectAside() {
  if (document.querySelector(".clamps-bot-aside")) {
    return;
  }

  const prefix = imagePrefix();
  const mounts = document.querySelectorAll("[data-clamps-bot-mount]");

  if (mounts.length) {
    mounts.forEach((mount) => {
      const compact = mount.dataset.clampsBot === "compact";
      mount.outerHTML = renderClampsBotAside({ compact, imagePrefix: prefix });
    });
    return;
  }

  const mode = document.body.dataset.clampsBot;
  if (!mode) {
    return;
  }

  const main = document.querySelector("main");
  if (!main) {
    return;
  }

  const compact = mode === "compact";
  const position = document.body.dataset.clampsBotPosition === "end" ? "beforeend" : "afterbegin";

  main.insertAdjacentHTML(
    position,
    renderClampsBotAside({ compact, imagePrefix: prefix })
  );
}

document.querySelectorAll(".site-footer").forEach((footer) => {
  if (footer.querySelector(".clamps-bot-footer")) {
    return;
  }

  footer.insertAdjacentHTML(
    "afterbegin",
    renderClampsBotFooter({ imagePrefix: imagePrefix() })
  );
});

injectAside();
