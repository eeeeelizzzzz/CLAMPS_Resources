export const SPLASH_STORYMAP_URL =
  "https://storymaps.arcgis.com/stories/093640ac6bdc479394d7fd9c7068fd27";

const SUPER_POWER =
  "A hero with many sensors, Multitron keeps a continuous eye on the temperature, humidity, clouds and winds in the lower atmosphere, helping to provide early warning of impending storms.";

const SCIENCE_SCOOP =
  "This trailer is home to the three main instruments that comprise CLAMPS. A Doppler lidar uses a non-visible laser to measure wind speed in the lowest parts of the atmosphere, and a meteorology station measures surface weather conditions. Two passive sensors (the atmospheric emitted radiance interferometer and microwave radiometer) “listen” for signals to measure downwelling radiance from the atmosphere, used to retrieve temperature and moisture profiles.";

function clampsBotImage(imagePrefix) {
  return `
    <img
      src="${imagePrefix}images/outreach/CLAMPS-bot.png"
      alt="CLAMPS Bot mascot — formally Multitron"
      class="clamps-bot-aside__img"
      loading="lazy"
      width="960"
      height="1280"
    >
  `;
}

function storyMapLink(className = "clamps-bot-aside__storymap") {
  return `
    <a
      href="${SPLASH_STORYMAP_URL}"
      class="${className}"
      target="_blank"
      rel="noopener noreferrer"
    >Superheroes of SPLASH StoryMap →</a>
  `;
}

export function renderClampsBotAside({ compact = false, imagePrefix = "" } = {}) {
  const compactClass = compact ? " clamps-bot-aside--compact" : "";

  if (compact) {
    return `
      <aside class="clamps-bot-aside clamps-bot-aside--outreach${compactClass}">
        <div class="clamps-bot-aside__panel">
          ${clampsBotImage(imagePrefix)}
          <div class="clamps-bot-aside__body">
            <strong class="clamps-bot-aside__title">Meet CLAMPS Bot</strong>
            <p class="clamps-bot-aside__formal">
              Formally <em>Multitron</em> · <em>Superheroes of SPLASH</em> (from NOAA PSL) outreach
            </p>
            <p class="clamps-bot-aside__lead">${SUPER_POWER}</p>
            ${storyMapLink()}
          </div>
        </div>
      </aside>
    `;
  }

  return `
    <aside class="clamps-bot-aside clamps-bot-aside--outreach${compactClass}">
      <div class="clamps-bot-aside__panel">
        ${clampsBotImage(imagePrefix)}
        <div class="clamps-bot-aside__body">
          <strong class="clamps-bot-aside__title">Meet CLAMPS Bot</strong>
          <p class="clamps-bot-aside__formal">
            Formally <em>Multitron</em> — outreach hero from
            <em>Superheroes of SPLASH</em> (from NOAA PSL) StoryMap, part of the SPLASH-SAIL education effort.
          </p>
          <dl class="clamps-bot-aside__facts">
            <div>
              <dt>Super Power</dt>
              <dd>${SUPER_POWER}</dd>
            </div>
            <div>
              <dt>Science Scoop</dt>
              <dd>${SCIENCE_SCOOP}</dd>
            </div>
          </dl>
          ${storyMapLink()}
        </div>
      </div>
    </aside>
  `;
}

export function renderClampsBotFooter({ imagePrefix = "" } = {}) {
  return `
    <p class="clamps-bot-footer">
      <img
        src="${imagePrefix}images/outreach/CLAMPS-bot.png"
        alt=""
        width="48"
        height="64"
        loading="lazy"
      >
      <span>
        <a href="${SPLASH_STORYMAP_URL}" target="_blank" rel="noopener noreferrer">CLAMPS Bot</a>
        (Multitron) · <em>Superheroes of SPLASH</em> (from NOAA PSL)
      </span>
    </p>
  `;
}
