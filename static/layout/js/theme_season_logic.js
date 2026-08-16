//gipcco_project\static\layout\js\theme_season_logic.js
document.addEventListener("DOMContentLoaded", function () {
  // --- Theme Switcher & Seasonal Logic ---
  const themeSwitch = document.getElementById("darkModeSwitch");
  const themeLabel = document.getElementById("darkModeLabel");
  const htmlElement = document.documentElement;

  function setTheme(theme) {
    htmlElement.setAttribute("data-bs-theme", theme);
    localStorage.setItem("theme", theme);
    themeSwitch.checked = theme === "dark";
    themeLabel.innerHTML =
      theme === "dark"
        ? '<i class="bi bi-sun-fill text-warning"></i>'
        : '<i class="bi bi-moon-stars-fill"></i>';
  }

  themeSwitch.addEventListener("change", () => {
    setTheme(themeSwitch.checked ? "dark" : "light");
  });

  const currentTheme = localStorage.getItem("theme") || "light";
  setTheme(currentTheme);

  const seasonToggle = document.getElementById("seasonToggle");
  const celestialBody = document.getElementById("celestial");
  const seasonIndicator = document.getElementById("seasonIndicator");
  const body = document.body;
  const seasons = ["winter", "spring", "summer", "autumn"];
  const seasonNames = {
    winter: "Winter",
    spring: "Spring",
    summer: "Summer",
    autumn: "Autumn",
  };
  const currentSeason = localStorage.getItem("season") || null;
  let seasonalModeEnabled =
    localStorage.getItem("seasonalModeEnabled") === "true";
  let seasonIndex = currentSeason ? seasons.indexOf(currentSeason) : 0;

  function applySeason(season) {
    body.classList.remove(
      "seasonal-mode",
      "spring-mode",
      "summer-mode",
      "autumn-mode"
    );
    if (seasonalModeEnabled && season) {
      body.classList.add("seasonal-mode");
      if (season === "spring") body.classList.add("spring-mode");
      else if (season === "summer") body.classList.add("summer-mode");
      else if (season === "autumn") body.classList.add("autumn-mode");
      else body.classList.add("seasonal-mode");
      localStorage.setItem("season", season);
      createPrecipitation();
      showSeasonIndicator(seasonNames[season]);
    } else {
      body.style.backgroundImage = "";
      localStorage.removeItem("season");
    }
  }

  function showSeasonIndicator(seasonName) {
    seasonIndicator.textContent = seasonName;
    seasonIndicator.classList.add("show");
    setTimeout(() => {
      seasonIndicator.classList.remove("show");
    }, 2000);
  }

  if (seasonalModeEnabled && currentSeason) {
    applySeason(currentSeason);
  }

  function changeSeason() {
    if (!seasonalModeEnabled) {
      seasonalModeEnabled = true;
      localStorage.setItem("seasonalModeEnabled", "true");
      showSeasonIndicator("Seasonal Theme Enabled!");
    }
    seasonIndex = (seasonIndex + 1) % seasons.length;
    applySeason(seasons[seasonIndex]);
  }

  celestialBody.addEventListener("click", changeSeason);
  seasonToggle.addEventListener("click", changeSeason);

  function createPrecipitation() {
    if (!seasonalModeEnabled) return;
    const container = document.getElementById("precipitation");
    container.innerHTML = "";
    const numElements = 30;
    for (let i = 0; i < numElements; i++) {
      const element = document.createElement("div");
      element.className = "precipitation-element";
      element.style.left = Math.random() * 100 + "%";
      element.style.animationDelay = Math.random() * 2 + "s";
      element.style.animationDuration = Math.random() * 2 + 3 + "s";
      element.style.opacity = Math.random() * 0.4 + 0.2;
      container.appendChild(element);
    }
  }

  if (seasonalModeEnabled) {
    createPrecipitation();
  }

  window.addEventListener("scroll", () => {
    if (!seasonalModeEnabled) return;
    const celestial = document.getElementById("celestial");
    const scrolled = window.pageYOffset;
    const rate = scrolled * -0.3;
    celestial.style.transform = `translateY(${rate}px)`;
  });

  const brandLogo = document.querySelector(".navbar-brand");
  let clickCount = 0;
  let clickTimer = null;
  brandLogo.addEventListener("click", () => {
    clickCount++;
    if (clickCount === 1) {
      clickTimer = setTimeout(() => {
        clickCount = 0;
      }, 1000);
    } else if (clickCount === 3) {
      clearTimeout(clickTimer);
      clickCount = 0;
      if (!seasonalModeEnabled) {
        seasonalModeEnabled = true;
        localStorage.setItem("seasonalModeEnabled", "true");
        applySeason(seasons[seasonIndex]);
        showSeasonIndicator("Seasonal Theme Enabled!");
      }
      seasonToggle.style.opacity = "1";
      seasonToggle.style.transform = "scale(1.2)";
      setTimeout(() => {
        seasonToggle.style.opacity = "0.2";
        seasonToggle.style.transform = "scale(1)";
      }, 3000);
    }
  });
});