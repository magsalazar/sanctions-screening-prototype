(() => {
  const records = JSON.parse(document.querySelector("#offline-records").textContent);
  const countrySearchAliases = JSON.parse(
    document.querySelector("#offline-country-aliases").textContent
  );
  const form = document.querySelector("#f");
  const nameInput = document.querySelector("#n");
  const countryInput = document.querySelector("#c");
  const sourceInput = document.querySelector("#s");
  const pageSize = document.querySelector("#page-size");
  const message = document.querySelector("#m");
  const resultList = document.querySelector("#r");
  const searchPanel = document.querySelector("#search-panel");
  const resultSummary = document.querySelector("#results-summary");
  const pageSizeControl = document.querySelector("#page-size-control");
  const countryList = document.querySelector("#country-options");
  const countryOptions = Array.from(countryList.querySelectorAll('[role="option"]'));
  const pagination = document.querySelector("#pagination");
  const previousPage = document.querySelector("#previous-page");
  const nextPage = document.querySelector("#next-page");
  const pageIndicator = document.querySelector("#page-indicator");
  const languageButtons = Array.from(document.querySelectorAll("[data-language]"));
  const translations = window.OCHA_TRANSLATIONS;
  const snapshotNotice = document.querySelector("#snapshot-notice");
  let language = "en";
  let activeCountry = -1;
  let searchGeneration = 0;
  let currentPage = 1;
  let currentQuery = { name: "", country: "", source: "", page_size: "25" };
  let latestSearchResponse = null;
  let currentSearchMessage = null;

  function translate(key, values = {}) {
    const text = translations[language][key] || translations.en[key] || key;
    return text.replace(/\{(\w+)\}/g, (match, name) =>
      values[name] === undefined ? match : values[name]
    );
  }

  function formatNumber(value) {
    return new Intl.NumberFormat(language).format(Number(value) || 0);
  }

  function translateStatus(status) {
    const keys = {
      OK: "statusAvailable",
      NOT_CONFIGURED: "statusNotConfiguredTranslated",
      ERROR: "statusErrorTranslated",
      NOT_LOADED: "statusNotLoadedTranslated"
    };
    return translate(keys[status] || "statusNotLoadedTranslated");
  }

  function applyLanguage(selectedLanguage) {
    language = translations[selectedLanguage] ? selectedLanguage : "en";
    document.documentElement.lang = language;
    document.querySelectorAll("[data-i18n]").forEach(element => {
      element.textContent = translate(element.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(element => {
      element.placeholder = translate(element.dataset.i18nPlaceholder);
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach(element => {
      element.setAttribute("aria-label", translate(element.dataset.i18nAriaLabel));
    });
    languageButtons.forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.language === language));
    });
    document.querySelectorAll("[data-status]").forEach(element => {
      element.textContent = translateStatus(element.dataset.status);
    });
    document.querySelectorAll("[data-record-count]").forEach(element => {
      element.textContent = translate("recordsCount", {
        count: formatNumber(element.dataset.recordCount)
      });
    });
    document.querySelectorAll("[data-retrieved-at]").forEach(element => {
      const date = new Date(element.dataset.retrievedAt);
      element.textContent = Number.isNaN(date.getTime())
        ? element.dataset.retrievedAt
        : new Intl.DateTimeFormat(language, {
            dateStyle: "medium",
            timeStyle: "short"
          }).format(date);
    });
    document.querySelectorAll("[data-status-message]").forEach(element => {
      const statusMessage = element.dataset.statusMessage;
      element.textContent =
        statusMessage === "UNGM integration requires an authorized HTTPS endpoint and UNGM_API_TOKEN"
          ? translate("ungmConfigurationMessage")
          : statusMessage;
    });
    snapshotNotice.textContent = translate("offlineSnapshotNotice", {
      date: snapshotNotice.dataset.generatedAt
    });
    if (currentSearchMessage) {
      showSearchMessage(
        currentSearchMessage.key,
        currentSearchMessage.values,
        currentSearchMessage.showPageSize
      );
    }
    if (latestSearchResponse) {
      renderSearchResponse(latestSearchResponse);
    }
  }

  function showSearchMessage(key, values = {}, showPageSize = false) {
    currentSearchMessage = { key, values, showPageSize };
    resultSummary.hidden = false;
    pageSizeControl.hidden = !showPageSize;
    message.textContent = translate(key, values);
  }

  function closeCountrySuggestions() {
    countryList.hidden = true;
    countryInput.setAttribute("aria-expanded", "false");
    countryInput.removeAttribute("aria-activedescendant");
    activeCountry = -1;
  }

  function normalizeCountrySearch(value) {
    return value
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase()
      .replace(/[^a-z0-9]/g, "");
  }

  function updateCountrySuggestions() {
    const prefix = normalizeCountrySearch(countryInput.value.trim());
    let shown = 0;
    countryOptions.forEach(option => {
      const aliases = option.dataset.searchAliases.split("|").filter(Boolean);
      const matches =
        normalizeCountrySearch(option.dataset.country).includes(prefix) ||
        aliases.some(alias => normalizeCountrySearch(alias).includes(prefix));
      const visible = matches && (prefix !== "" || shown < 8);
      option.hidden = !visible;
      option.setAttribute("aria-selected", "false");
      if (visible) shown++;
    });
    countryList.hidden = shown === 0;
    countryInput.setAttribute("aria-expanded", String(shown > 0));
    countryInput.removeAttribute("aria-activedescendant");
    activeCountry = -1;
  }

  function chooseCountry(option) {
    countryInput.value = option.dataset.country;
    closeCountrySuggestions();
    countryInput.focus();
  }

  function setActiveCountry(index) {
    const visibleOptions = countryOptions.filter(option => !option.hidden);
    if (!visibleOptions.length) return;
    activeCountry = (index + visibleOptions.length) % visibleOptions.length;
    countryOptions.forEach(option => option.setAttribute("aria-selected", "false"));
    const option = visibleOptions[activeCountry];
    option.setAttribute("aria-selected", "true");
    countryInput.setAttribute("aria-activedescendant", option.id);
    option.scrollIntoView({ block: "nearest" });
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[character]);
  }

  function safeSourceUrl(value) {
    try {
      const url = new URL(String(value));
      return url.protocol === "https:" ? url.href : "#";
    } catch {
      return "#";
    }
  }

  function countryMatches(record, query) {
    const tokens = (record.country || "")
      .split("|")
      .map(value => normalizeCountrySearch(value.trim()))
      .filter(Boolean);
    const knownTerms = countrySearchAliases[normalizeCountrySearch(query)];
    if (knownTerms) {
      const accepted = new Set(knownTerms.map(normalizeCountrySearch));
      return tokens.some(token => accepted.has(token));
    }
    const prefix = normalizeCountrySearch(query);
    return tokens.some(token => token.startsWith(prefix));
  }

  function loadResults(page, scrollToSearch = false) {
    const generation = ++searchGeneration;
    latestSearchResponse = null;
    showSearchMessage("searching");
    resultList.innerHTML = "";
    pagination.hidden = true;

    window.setTimeout(() => {
      if (generation !== searchGeneration) return;
      const query = currentQuery.name.toLocaleLowerCase();
      const matches = records.filter(record =>
        (!query ||
          String(record.name || "").toLocaleLowerCase().includes(query) ||
          String(record.aliases || "").toLocaleLowerCase().includes(query)) &&
        (!currentQuery.country || countryMatches(record, currentQuery.country)) &&
        (!currentQuery.source || record.source === currentQuery.source)
      );
      const count = matches.length;
      const showAll = currentQuery.page_size === "all";
      const size = showAll ? count : Number(currentQuery.page_size);
      const totalPages = showAll ? 1 : Math.max(1, Math.ceil(count / size));
      currentPage = showAll ? 1 : Math.min(page, totalPages);
      const offset = showAll ? 0 : (currentPage - 1) * size;
      const results = matches.slice(offset, showAll ? undefined : offset + size);
      latestSearchResponse = {
        results,
        count,
        page: currentPage,
        page_size: size,
        total_pages: totalPages,
        has_previous: currentPage > 1,
        has_next: currentPage < totalPages
      };
      renderSearchResponse(latestSearchResponse);
      if (scrollToSearch) {
        searchPanel.scrollIntoView({ behavior: "instant", block: "start" });
      }
    }, 0);
  }

  function renderSearchResponse(response) {
    currentPage = response.page;
    if (response.count === 0) {
      showSearchMessage("noMatchingRecords");
      resultList.innerHTML = `<p>${escapeHtml(translate("noMatchesLoaded"))}</p>`;
      pagination.hidden = true;
      return;
    }
    const first = (response.page - 1) * response.page_size + 1;
    const last = first + response.results.length - 1;
    showSearchMessage(response.count === 1 ? "resultSummaryOne" : "resultSummary", {
      first: formatNumber(first),
      last: formatNumber(last),
      count: formatNumber(response.count)
    }, true);
    const entityTypes = {
      individual: "entityIndividual",
      entity: "entityEntity",
      organization: "entityOrganization",
      vessel: "entityVessel"
    };
    resultList.innerHTML = response.results.map(record => {
      const sourceKey = `sourceShort_${record.source}`;
      const sourceName = translations[language][sourceKey] || record.source;
      const typeKey = entityTypes[String(record.entity_type || "").toLowerCase()];
      return `<article><h3>${escapeHtml(record.name)}</h3><dl><dt>${escapeHtml(translate("resultSource"))}</dt><dd>${escapeHtml(sourceName)}</dd><dt>${escapeHtml(translate("resultType"))}</dt><dd>${escapeHtml(typeKey ? translate(typeKey) : translate("notSpecified"))}</dd><dt>${escapeHtml(translate("resultCountry"))}</dt><dd>${escapeHtml(record.country || translate("notSpecified"))}</dd><dt>${escapeHtml(translate("resultAliases"))}</dt><dd>${escapeHtml(record.aliases || translate("noneShown"))}</dd><dt>${escapeHtml(translate("resultProgramme"))}</dt><dd>${escapeHtml(record.programmes || translate("notSpecified"))}</dd><dt>${escapeHtml(translate("resultReference"))}</dt><dd>${escapeHtml(record.source_ref || translate("notSpecified"))}</dd></dl><a href="${escapeHtml(safeSourceUrl(record.source_url))}" target="_blank" rel="noopener"><span>${escapeHtml(translate("openOfficialSource"))}</span> ↗</a></article>`;
    }).join("");
    pageIndicator.textContent = translate("pageIndicator", {
      page: formatNumber(response.page),
      total: formatNumber(response.total_pages)
    });
    previousPage.disabled = !response.has_previous;
    nextPage.disabled = !response.has_next;
    pagination.hidden = response.total_pages <= 1;
  }

  countryInput.addEventListener("focus", updateCountrySuggestions);
  countryInput.addEventListener("input", updateCountrySuggestions);
  countryInput.addEventListener("keydown", event => {
    if (event.key === "ArrowDown" && !countryList.hidden) {
      event.preventDefault();
      setActiveCountry(activeCountry + 1);
    } else if (event.key === "ArrowUp" && !countryList.hidden) {
      event.preventDefault();
      setActiveCountry(activeCountry < 0 ? -1 : activeCountry - 1);
    } else if (event.key === "Enter" && activeCountry >= 0) {
      event.preventDefault();
      chooseCountry(countryOptions.find(option => option.getAttribute("aria-selected") === "true"));
    } else if (event.key === "Escape") {
      closeCountrySuggestions();
    }
  });
  countryInput.addEventListener("blur", () => window.setTimeout(closeCountrySuggestions, 0));
  countryList.addEventListener("pointerdown", event => {
    const option = event.target.closest('[role="option"]');
    if (!option) return;
    event.preventDefault();
    chooseCountry(option);
  });
  document.addEventListener("pointerdown", event => {
    if (!event.target.closest(".country-control")) closeCountrySuggestions();
  });

  form.addEventListener("reset", () => {
    searchGeneration++;
    currentQuery = { name: "", country: "", source: "", page_size: "25" };
    currentPage = 1;
    latestSearchResponse = null;
    currentSearchMessage = null;
    closeCountrySuggestions();
    message.textContent = "";
    resultList.innerHTML = "";
    resultSummary.hidden = true;
    pageSizeControl.hidden = true;
    pageSize.value = "25";
    pagination.hidden = true;
    window.setTimeout(() => nameInput.focus(), 0);
  });

  form.addEventListener("submit", event => {
    event.preventDefault();
    const name = nameInput.value.trim();
    const country = countryInput.value.trim();
    if (!name && !country) {
      searchGeneration++;
      latestSearchResponse = null;
      showSearchMessage("enterNameOrCountry");
      resultList.innerHTML = "";
      pagination.hidden = true;
      return;
    }
    if (name.length === 1) {
      searchGeneration++;
      latestSearchResponse = null;
      showSearchMessage("minimumNameLength");
      resultList.innerHTML = "";
      pagination.hidden = true;
      return;
    }
    currentQuery = {
      name,
      country,
      source: sourceInput.value,
      page_size: pageSize.value
    };
    loadResults(1);
  });

  pageSize.addEventListener("change", () => {
    currentQuery.page_size = pageSize.value;
    loadResults(1);
  });
  previousPage.addEventListener("click", () => loadResults(currentPage - 1, true));
  nextPage.addEventListener("click", () => loadResults(currentPage + 1, true));
  languageButtons.forEach(button => {
    button.addEventListener("click", () => applyLanguage(button.dataset.language));
  });

  applyLanguage("en");
})();
