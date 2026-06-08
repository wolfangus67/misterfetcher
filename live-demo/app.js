const state = {
    currentSection: "addons",
    loggedIn: false,
    filter: "all",
    runTimer: null,
    runProgress: 0,
    moviePrefetched: 0,
    seriesPrefetched: 0,
    movieCached: 0,
    seriesCached: 0,
    currentCatalogIndex: 0,
    settings: {
        moviesPerCatalog: 50,
        seriesPerCatalog: 50,
        mixedPerCatalog: 50,
        delay: 2,
        runLimit: "Unlimited"
    },
    schedule: {
        enabled: true,
        days: ["Mon", "Tue", "Wed", "Thu", "Fri"],
        time: "02:00"
    },
    addons: [
        { id: "catalog-addon", title: "Addon Catalogue", type: "catalog", source: "https://example.com/catalogue/addon.json", enabled: true },
        { id: "aiostream-addon", title: "Aiostream", type: "aiostream", source: "https://example.com/aiostream/manifest.json", enabled: true }
    ],
    catalogs: [
        { id: "cinema-essentials", title: "Cinema Essentials", type: "movie", enabled: true, home: true },
        { id: "series-radar", title: "Series Radar", type: "series", enabled: true, home: true },
        { id: "weekend-picks", title: "Weekend Picks", type: "mixed", enabled: false, home: false },
        { id: "doc-shelf", title: "Documentary Shelf", type: "movie", enabled: true, home: false },
        { id: "anime-track", title: "Anime Track", type: "series", enabled: true, home: true },
        { id: "festival-mix", title: "Festival Mix", type: "mixed", enabled: true, home: false },
        { id: "family-night", title: "Family Night", type: "movie", enabled: true, home: true },
        { id: "late-shift", title: "Late Shift", type: "series", enabled: true, home: false },
        { id: "arthouse-loop", title: "Arthouse Loop", type: "movie", enabled: false, home: false },
        { id: "binge-stack", title: "Binge Stack", type: "series", enabled: true, home: true },
        { id: "premiere-board", title: "Premiere Board", type: "mixed", enabled: true, home: true },
        { id: "quiet-rewind", title: "Quiet Rewind", type: "movie", enabled: false, home: false }
    ],
    runPool: [
        { title: "Premiere Board", subtitle: "Release wave from overlapping catalogs", mediaType: "mixed", bucket: "cached-series" },
        { title: "Cinema Essentials", subtitle: "Action movie ready for prefetch", mediaType: "movie", bucket: "prefetched-movie" },
        { title: "Series Radar", subtitle: "High demand series in queue", mediaType: "series", bucket: "prefetched-series" },
        { title: "Documentary Shelf", subtitle: "Already present in local cache", mediaType: "movie", bucket: "cached-movie" },
        { title: "Anime Track", subtitle: "Series entry already scanned in another catalog", mediaType: "series", bucket: "cached-series" },
        { title: "Family Night", subtitle: "Movie artwork prepared for fetch", mediaType: "movie", bucket: "prefetched-movie" }
    ]
};

const elements = {
    navItems: [...document.querySelectorAll(".nav-item")],
    sectionPanels: [...document.querySelectorAll(".section-panel")],
    filterChips: [...document.querySelectorAll(".filter-chip")],
    addonGrid: document.getElementById("addonGrid"),
    catalogGrid: document.getElementById("catalogGrid"),
    loginForm: document.getElementById("loginForm"),
    accountSummary: document.getElementById("accountSummary"),
    accountName: document.getElementById("accountName"),
    avatarBadge: document.getElementById("avatarBadge"),
    catalogManifestCount: document.getElementById("catalogManifestCount"),
    streamLinkLed: document.getElementById("streamLinkLed"),
    streamLinkText: document.getElementById("streamLinkText"),
    streamLinkAction: document.getElementById("streamLinkAction"),
    usernameInput: document.getElementById("usernameInput"),
    loginButton: document.getElementById("loginButton"),
    registerButton: document.getElementById("registerButton"),
    logoutButton: document.getElementById("logoutButton"),
    brandHomeButton: document.getElementById("brandHomeButton"),
    addCatalogAddonButton: document.getElementById("addCatalogAddonButton"),
    addStreamAddonButton: document.getElementById("addStreamAddonButton"),
    addonFeedback: document.getElementById("addonFeedback"),
    moviesPerCatalogInput: document.getElementById("moviesPerCatalogInput"),
    seriesPerCatalogInput: document.getElementById("seriesPerCatalogInput"),
    mixedPerCatalogInput: document.getElementById("mixedPerCatalogInput"),
    delayInput: document.getElementById("delayInput"),
    delayValue: document.getElementById("delayValue"),
    runLimitInput: document.getElementById("runLimitInput"),
    scheduleToggle: document.getElementById("scheduleToggle"),
    daysPicker: document.getElementById("daysPicker"),
    runTimeInput: document.getElementById("runTimeInput"),
    applySettingsButton: document.getElementById("applySettingsButton"),
    randomizeButton: document.getElementById("randomizeButton"),
    runTitle: document.getElementById("runTitle"),
    runStatusPill: document.getElementById("runStatusPill"),
    runAlert: document.getElementById("runAlert"),
    runAlertTitle: document.getElementById("runAlertTitle"),
    runAlertText: document.getElementById("runAlertText"),
    meterProgress: document.getElementById("meterProgress"),
    meterPercent: document.getElementById("meterPercent"),
    currentCatalogLabel: document.getElementById("currentCatalogLabel"),
    moviesPrefetched: document.getElementById("moviesPrefetched"),
    seriesPrefetched: document.getElementById("seriesPrefetched"),
    totalPrefetched: document.getElementById("totalPrefetched"),
    totalAlreadyPrefetched: document.getElementById("totalAlreadyPrefetched"),
    startRunButton: document.getElementById("startRunButton"),
    stopRunButton: document.getElementById("stopRunButton"),
    logStream: document.getElementById("logStream"),
    posterType: document.getElementById("posterType"),
    posterTitle: document.getElementById("posterTitle"),
    posterSubtitle: document.getElementById("posterSubtitle"),
    posterArt: document.getElementById("posterArt")
};

function initialsFromName(name) {
    return (
        name
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2)
            .map(part => part[0].toUpperCase())
            .join("") || "MF"
    );
}

function logLine(message) {
    const line = document.createElement("div");
    const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    line.className = "log-line";
    line.innerHTML = `<strong>[${time}]</strong> ${message}`;
    elements.logStream.appendChild(line);
    while (elements.logStream.children.length > 10) {
        elements.logStream.removeChild(elements.logStream.firstChild);
    }
}

function enabledCatalogs() {
    return state.catalogs.filter(catalog => catalog.enabled);
}

function updateAccountHealth() {
    const catalogManifests = state.addons.filter(addon => addon.type === "catalog" && addon.source.trim()).length;
    const hasLinkedStream = state.addons.some(
        addon => addon.type === "aiostream" && addon.enabled && addon.source.trim()
    );

    elements.catalogManifestCount.textContent = String(catalogManifests);
    elements.streamLinkAction.classList.toggle("health-actionable", !hasLinkedStream);
    elements.streamLinkLed.classList.toggle("status-led-green", hasLinkedStream);
    elements.streamLinkLed.classList.toggle("status-led-red", !hasLinkedStream);
    elements.streamLinkText.textContent = hasLinkedStream ? "Ready" : "Add manifest";
    elements.streamLinkAction.tabIndex = hasLinkedStream ? -1 : 0;
    elements.streamLinkAction.setAttribute("role", hasLinkedStream ? "presentation" : "button");
    elements.streamLinkAction.setAttribute(
        "aria-label",
        hasLinkedStream ? "Aiostream manifest ready" : "Open addons to add aiostream manifest"
    );
    updateRunAvailabilityState();
}

function showAddonFeedback(message) {
    elements.addonFeedback.textContent = message;
    elements.addonFeedback.classList.remove("hidden");
    clearTimeout(showAddonFeedback.timer);
    showAddonFeedback.timer = setTimeout(() => {
        elements.addonFeedback.classList.add("hidden");
    }, 2400);
}

function hasActiveCatalogAddon() {
    return state.addons.some(addon => addon.type === "catalog" && addon.enabled && addon.source.trim());
}

function hasActiveStreamAddon() {
    return state.addons.some(addon => addon.type === "aiostream" && addon.enabled && addon.source.trim());
}

function updateRunAvailabilityState() {
    if (state.runTimer) {
        return;
    }

    if (!hasActiveCatalogAddon()) {
        elements.runTitle.textContent = "Missing catalog addon";
        elements.runStatusPill.textContent = "Blocked";
        elements.runAlertTitle.textContent = "Missing catalog addon";
        elements.runAlertText.textContent = "Click here to open Addons and add or enable a catalog manifest.";
        elements.runAlert.dataset.target = "catalog";
        elements.runAlert.classList.remove("hidden");
        return;
    }

    if (!hasActiveStreamAddon()) {
        elements.runTitle.textContent = "Missing aiostream addon";
        elements.runStatusPill.textContent = "Blocked";
        elements.runAlertTitle.textContent = "Missing aiostream addon";
        elements.runAlertText.textContent = "Click here to open Addons and add or enable an aiostream manifest.";
        elements.runAlert.dataset.target = "aiostream";
        elements.runAlert.classList.remove("hidden");
        return;
    }

    elements.runTitle.textContent = "Ready to prefetch";
    elements.runStatusPill.textContent = "Idle";
    elements.runAlert.dataset.target = "";
    elements.runAlert.classList.add("hidden");
}

function setSection(sectionName) {
    state.currentSection = sectionName;
    elements.navItems.forEach(item => {
        item.classList.toggle("active", item.dataset.target === sectionName);
    });
    elements.sectionPanels.forEach(panel => {
        panel.classList.toggle("section-hidden", panel.dataset.section !== sectionName);
    });
}

function setLoggedIn(loggedIn) {
    state.loggedIn = loggedIn;
    elements.loginForm.classList.toggle("hidden", loggedIn);
    elements.accountSummary.classList.toggle("hidden", !loggedIn);
    const name = elements.usernameInput.value.trim() || "guest";
    elements.accountName.textContent = name;
    elements.avatarBadge.textContent = initialsFromName(name);
}

function renderAddons() {
    const groups = [
        { type: "catalog", label: "Addon Catalog" },
        { type: "aiostream", label: "Addon Stream" }
    ];

    elements.addonGrid.innerHTML = "";

    groups.forEach(group => {
        const section = document.createElement("section");
        section.className = "addon-group";
        section.innerHTML = `
            <div class="addon-group-head">
                <div>
                    <p class="eyebrow">${group.label}</p>
                    <strong>${group.type === "catalog" ? "Catalog JSON sources" : "Aiostream JSON sources"}</strong>
                </div>
            </div>
            <div class="addon-list" data-addon-group="${group.type}"></div>
        `;

        const list = section.querySelector("[data-addon-group]");
        state.addons
            .filter(addon => addon.type === group.type)
            .forEach(addon => {
                const row = document.createElement("div");
                row.className = `addon-row${addon.enabled ? "" : " disabled"}`;
                row.innerHTML = `
                    <div class="addon-row-main">
                        <label>
                            <span>Name</span>
                            <input type="text" value="${addon.title}" data-addon-field="title" data-addon-id="${addon.id}">
                        </label>
                        <label>
                            <span>Manifest URL</span>
                            <input type="text" value="${addon.source}" data-addon-field="source" data-addon-id="${addon.id}">
                        </label>
                        <div class="addon-row-actions">
                            <button class="toggle ${addon.enabled ? "on" : ""}" data-addon-toggle="${addon.id}" aria-label="Toggle addon"></button>
                            <span class="addon-enabled-label">Enabled</span>
                            <button class="button danger" data-addon-delete="${addon.id}">Delete</button>
                        </div>
                    </div>
                    <div class="addon-row-meta">${addon.type === "catalog" ? "catalog" : "stream"} addon</div>
                `;
                list.appendChild(row);
            });

        elements.addonGrid.appendChild(section);
    });
    updateAccountHealth();
}

function renderCatalogs() {
    const catalogs = state.catalogs.filter(catalog => {
        if (state.filter === "all") return true;
        if (state.filter === "home") return catalog.home;
        return catalog.type === state.filter;
    });

    elements.catalogGrid.innerHTML = `
        <div class="table-head">
            <span>Name</span>
            <span>Type</span>
            <span>Status</span>
        </div>
    `;

    catalogs.forEach(catalog => {
        const row = document.createElement("div");
        row.className = `table-row compact${catalog.enabled ? "" : " disabled"}`;
        row.innerHTML = `
            <strong>${catalog.title}</strong>
            <span class="tag">${catalog.type}</span>
            <button class="toggle ${catalog.enabled ? "on" : ""}" data-catalog-id="${catalog.id}" aria-label="Toggle catalog"></button>
        `;
        elements.catalogGrid.appendChild(row);
    });
}

function renderScheduleControls() {
    const weekDays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    elements.scheduleToggle.classList.toggle("on", state.schedule.enabled);
    elements.runTimeInput.value = state.schedule.time;
    elements.daysPicker.innerHTML = "";

    weekDays.forEach(day => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = `day-chip${state.schedule.days.includes(day) ? " active" : ""}`;
        chip.dataset.day = day;
        chip.textContent = day;
        elements.daysPicker.appendChild(chip);
    });
}

function syncSettingsFromInputs() {
    state.settings.moviesPerCatalog = Number(elements.moviesPerCatalogInput.value || 50);
    state.settings.seriesPerCatalog = Number(elements.seriesPerCatalogInput.value || 50);
    state.settings.mixedPerCatalog = Number(elements.mixedPerCatalogInput.value || 50);
    state.settings.delay = Math.min(5, Math.max(1, Number(elements.delayInput.value || 2)));
    state.settings.runLimit = (elements.runLimitInput.value || "Unlimited").trim() || "Unlimited";
    elements.delayInput.value = String(state.settings.delay);
    elements.delayValue.textContent = `${state.settings.delay}s`;
    elements.runLimitInput.value = state.settings.runLimit;
}

function reflectRunState(mode) {
    elements.runStatusPill.textContent = mode;
}

function resetRun() {
    if (state.runTimer) {
        clearInterval(state.runTimer);
        state.runTimer = null;
    }
    state.runProgress = 0;
    state.moviePrefetched = 0;
    state.seriesPrefetched = 0;
    state.movieCached = 0;
    state.seriesCached = 0;
    state.currentCatalogIndex = 0;
    elements.meterProgress.style.width = "0%";
    elements.meterPercent.textContent = "0%";
    elements.currentCatalogLabel.textContent = "None";
    elements.moviesPrefetched.textContent = "0";
    elements.seriesPrefetched.textContent = "0";
    elements.totalPrefetched.textContent = "0";
    elements.totalAlreadyPrefetched.textContent = "0";
    elements.posterType.textContent = "Movie";
    elements.posterTitle.textContent = "Waiting for run";
    elements.posterSubtitle.textContent = "No title currently being prefetched";
    elements.posterArt.dataset.type = "idle";
    updateRunAvailabilityState();
}

function startRun() {
    resetRun();
    const enabled = enabledCatalogs();
    const hasCatalogAddon = hasActiveCatalogAddon();
    const hasStreamAddon = hasActiveStreamAddon();

    if (!hasCatalogAddon || !hasStreamAddon) {
        logLine("Prefetch requires at least one <strong>catalog addon</strong> and one <strong>stream addon</strong> enabled.");
        return;
    }

    if (!enabled.length) {
        elements.runTitle.textContent = "No catalog enabled";
        elements.runStatusPill.textContent = "Blocked";
        elements.runAlertTitle.textContent = "No catalog enabled";
        elements.runAlertText.textContent = "Click here to open Catalogs and enable at least one catalog.";
        elements.runAlert.dataset.target = "catalogs";
        elements.runAlert.classList.remove("hidden");
        logLine("No enabled catalogs available. Enable at least one catalog before launching a run.");
        return;
    }

    elements.runTitle.textContent = "Prefetch simulation in progress";
    reflectRunState("Running");
    elements.runAlert.classList.add("hidden");
    logLine(`Started demo prefetch with <strong>${enabled.length}</strong> enabled catalogs.`);

    state.runTimer = setInterval(() => {
        state.runProgress += 6 + Math.round(Math.random() * 8);
        if (state.runProgress > 100) {
            state.runProgress = 100;
        }

        state.currentCatalogIndex = Math.min(enabled.length - 1, Math.floor((state.runProgress / 100) * enabled.length));

        const currentCatalog = enabled[state.currentCatalogIndex];
        const currentItem = state.runPool[(Math.floor(state.runProgress / 14) + state.currentCatalogIndex) % state.runPool.length];
        elements.currentCatalogLabel.textContent = currentCatalog.title;
        elements.meterProgress.style.width = `${state.runProgress}%`;
        elements.meterPercent.textContent = `${state.runProgress}%`;
        elements.posterType.textContent = currentItem.mediaType;
        elements.posterTitle.textContent = currentItem.title;
        elements.posterSubtitle.textContent = currentItem.subtitle;
        elements.posterArt.dataset.type = currentItem.mediaType;

        if (currentItem.bucket === "prefetched-movie") {
            state.moviePrefetched += 1 + Math.round(Math.random() * 2);
        } else if (currentItem.bucket === "prefetched-series") {
            state.seriesPrefetched += 1 + Math.round(Math.random() * 2);
        } else if (currentItem.bucket === "cached-movie") {
            state.movieCached += 1 + Math.round(Math.random() * 2);
        } else {
            state.seriesCached += 1 + Math.round(Math.random() * 2);
        }

        elements.moviesPrefetched.textContent = String(state.moviePrefetched);
        elements.seriesPrefetched.textContent = String(state.seriesPrefetched);
        elements.totalPrefetched.textContent = String(state.moviePrefetched + state.seriesPrefetched);
        elements.totalAlreadyPrefetched.textContent = String(state.movieCached + state.seriesCached);

        if (state.runProgress === 100) {
            clearInterval(state.runTimer);
            state.runTimer = null;
            elements.runTitle.textContent = "Run complete";
            reflectRunState("Completed");
            logLine(
                `Completed demo run with <strong>${state.moviePrefetched}</strong> movies prefetched, <strong>${state.seriesPrefetched}</strong> series prefetched, <strong>${state.movieCached}</strong> movies already prefetched, and <strong>${state.seriesCached}</strong> series already prefetched.`
            );
        } else if (state.runProgress % 20 < 10) {
            logLine(`Processing <strong>${currentItem.title}</strong> from <strong>${currentCatalog.title}</strong>.`);
        }
    }, state.settings.delay * 260);
}

function randomizeDemo() {
    state.addons.forEach(addon => {
        addon.enabled = Math.random() > 0.25;
    });
    state.catalogs.forEach(catalog => {
        catalog.enabled = Math.random() > 0.35;
    });
    elements.moviesPerCatalogInput.value = String(25 + Math.round(Math.random() * 75));
    elements.seriesPerCatalogInput.value = String(25 + Math.round(Math.random() * 75));
    elements.mixedPerCatalogInput.value = String(25 + Math.round(Math.random() * 75));
    elements.delayInput.value = String(1 + Math.round(Math.random() * 4));
    elements.runLimitInput.value = ["Unlimited", "500", "1000", "2000"][Math.floor(Math.random() * 4)];
    syncSettingsFromInputs();
    renderAddons();
    renderCatalogs();
    logLine("Randomized the workspace for a denser config preview.");
}

function bindEvents() {
    elements.navItems.forEach(item => {
        item.addEventListener("click", () => {
            setSection(item.dataset.target);
        });
    });

    elements.brandHomeButton.addEventListener("click", () => {
        setSection("addons");
    });

    elements.filterChips.forEach(chip => {
        chip.addEventListener("click", () => {
            state.filter = chip.dataset.filter;
            elements.filterChips.forEach(other => other.classList.toggle("active", other === chip));
            renderCatalogs();
        });
    });

    elements.addonGrid.addEventListener("click", event => {
        const toggle = event.target.closest("[data-addon-toggle]");
        const deleteButton = event.target.closest("[data-addon-delete]");

        if (toggle) {
            const addon = state.addons.find(item => item.id === toggle.dataset.addonToggle);
            if (!addon) return;
            addon.enabled = !addon.enabled;
            renderAddons();
            logLine(`${addon.enabled ? "Enabled" : "Disabled"} <strong>${addon.title}</strong> addon.`);
            return;
        }

        if (deleteButton) {
            const addon = state.addons.find(item => item.id === deleteButton.dataset.addonDelete);
            if (!addon) return;
            state.addons = state.addons.filter(item => item.id !== addon.id);
            renderAddons();
            logLine(`Deleted <strong>${addon.title}</strong> addon.`);
        }
    });

    elements.addonGrid.addEventListener("input", event => {
        const field = event.target.dataset.addonField;
        const addonId = event.target.dataset.addonId;
        if (!field || !addonId) return;
        const addon = state.addons.find(item => item.id === addonId);
        if (!addon) return;
        addon[field] = event.target.value;
        updateAccountHealth();
    });

    elements.catalogGrid.addEventListener("click", event => {
        const toggle = event.target.closest("[data-catalog-id]");
        if (!toggle) return;
        const catalog = state.catalogs.find(item => item.id === toggle.dataset.catalogId);
        if (!catalog) return;
        catalog.enabled = !catalog.enabled;
        renderCatalogs();
        logLine(`${catalog.enabled ? "Enabled" : "Disabled"} <strong>${catalog.title}</strong> for this account.`);
    });

    elements.loginButton.addEventListener("click", () => {
        setLoggedIn(true);
        logLine(`Entered demo workspace as <strong>${elements.accountName.textContent}</strong>.`);
    });

    elements.registerButton.addEventListener("click", () => {
        setLoggedIn(true);
        logLine(`Created a new demo account called <strong>${elements.accountName.textContent}</strong>.`);
    });

    elements.logoutButton.addEventListener("click", () => {
        setLoggedIn(false);
        resetRun();
        logLine("Exited the demo session and returned to the account entry state.");
    });

    elements.delayInput.addEventListener("input", syncSettingsFromInputs);

    elements.scheduleToggle.addEventListener("click", () => {
        state.schedule.enabled = !state.schedule.enabled;
        renderScheduleControls();
        logLine(`Scheduler ${state.schedule.enabled ? "enabled" : "disabled"} for this account.`);
    });

    elements.streamLinkAction.addEventListener("click", () => {
        if (elements.streamLinkAction.classList.contains("health-actionable")) {
            setSection("addons");
            showAddonFeedback("Add an aiostream manifest to enable prefetch linking.");
        }
    });

    elements.streamLinkAction.addEventListener("keydown", event => {
        if (elements.streamLinkAction.classList.contains("health-actionable") && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            setSection("addons");
            showAddonFeedback("Add an aiostream manifest to enable prefetch linking.");
        }
    });

    elements.runAlert.addEventListener("click", () => {
        const target = elements.runAlert.dataset.target;
        if (!target) return;

        if (target === "catalogs") {
            setSection("catalogs");
            return;
        }

        setSection("addons");
        if (target === "aiostream") {
            showAddonFeedback("Add an aiostream manifest to enable prefetch linking.");
        } else if (target === "catalog") {
            showAddonFeedback("Add a catalog manifest to enable prefetch.");
        }
    });

    elements.daysPicker.addEventListener("click", event => {
        const chip = event.target.closest("[data-day]");
        if (!chip) return;
        const day = chip.dataset.day;
        if (state.schedule.days.includes(day)) {
            state.schedule.days = state.schedule.days.filter(item => item !== day);
        } else {
            state.schedule.days = [...state.schedule.days, day];
        }
        renderScheduleControls();
        logLine(`Updated scheduled days: <strong>${state.schedule.days.join(", ") || "none"}</strong>.`);
    });

    elements.runTimeInput.addEventListener("change", () => {
        state.schedule.time = elements.runTimeInput.value || "02:00";
        logLine(`Updated run time to <strong>${state.schedule.time}</strong>.`);
    });

    elements.addCatalogAddonButton.addEventListener("click", () => {
        const newAddon = {
            id: `catalog-addon-${Date.now()}`,
            title: "New Catalog Addon",
            type: "catalog",
            source: "https://example.com/catalogue/new-addon.json",
            enabled: true
        };
        state.addons.push(newAddon);
        renderAddons();
        showAddonFeedback("Catalog addon added and detected.");
        logLine("Added a new <strong>catalog addon</strong> row.");
    });

    elements.addStreamAddonButton.addEventListener("click", () => {
        const newAddon = {
            id: `stream-addon-${Date.now()}`,
            title: "New Stream Addon",
            type: "aiostream",
            source: "https://example.com/aiostream/manifest.json",
            enabled: true
        };
        state.addons.push(newAddon);
        renderAddons();
        showAddonFeedback("Aiostream addon added and detected.");
        logLine("Added a new <strong>stream addon</strong> row.");
    });

    elements.applySettingsButton.addEventListener("click", () => {
        syncSettingsFromInputs();
        logLine(
            `Applied preview settings: movies per catalog ${state.settings.moviesPerCatalog}, series per catalog ${state.settings.seriesPerCatalog}, mixed per catalog ${state.settings.mixedPerCatalog}, total items per run ${state.settings.runLimit}, delay ${state.settings.delay}s, episodes 0, schedule ${state.schedule.enabled ? "on" : "off"} at ${state.schedule.time}.`
        );
    });

    elements.randomizeButton.addEventListener("click", randomizeDemo);
    elements.startRunButton.addEventListener("click", startRun);
    elements.stopRunButton.addEventListener("click", () => {
        resetRun();
        logLine("Reset the demo run state.");
    });
}

function init() {
    setLoggedIn(false);
    setSection("addons");
    renderAddons();
    renderCatalogs();
    renderScheduleControls();
    updateAccountHealth();
    syncSettingsFromInputs();
    resetRun();
    bindEvents();
    logLine("Loaded live demo workspace.");
}

init();
