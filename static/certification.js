(() => {
  const requestForm = document.querySelector("#certification-request-form");
  const createRequestButton = document.querySelector("#create-certification-exercise");
  const resetRequestButton = document.querySelector("#reset-certification-request");
  const editRequestButton = document.querySelector("#edit-certification-request");
  const entityWorkflow = document.querySelector("#certification-entity-workflow");
  const entityForm = document.querySelector("#certification-entity-form");
  const entityList = document.querySelector("#certification-entity-list");
  const screeningButton = document.querySelector("#screen-certification-entities");
  const newReportButton = document.querySelector("#new-certification-exercise");
  const screeningStatus = document.querySelector("#certification-screening-status");
  const resultsPanel = document.querySelector("#certification-results");
  const reviewPanel = document.querySelector("#certification-review");
  const acknowledgement = document.querySelector("#certification-acknowledgement");
  const previewButton = document.querySelector("#preview-certification");
  const previewPanel = document.querySelector("#certification-preview");
  const fuzzyMatchingInput = document.querySelector("#cert-fuzzy-matching");
  const entityNameInput = document.querySelector("#cert-entity-name");
  const entityCategoryInput = document.querySelector("#cert-entity-category");
  const entityCountryInput = document.querySelector("#cert-entity-country");
  const entityIdentifiersInput = document.querySelector("#cert-entity-identifiers");
  const entityAliasesInput = document.querySelector("#cert-entity-aliases");
  const saveEntityButton = document.querySelector("#save-certification-entity");
  const resetEntityButton = document.querySelector("#reset-certification-entity");
  const cancelEditButton = document.querySelector("#cancel-certification-entity");
  const translations = window.OCHA_TRANSLATIONS;
  window.OCHACountryAutocomplete.initialize(document);
  const sources = Array.from(document.querySelectorAll(".certification-source-metadata [data-source-key]")).map(status => {
    const key = status.dataset.sourceKey;
    return {
      key,
      titleKey: `sourceTitle_${key}`,
      title: translations.en[`sourceTitle_${key}`] || key,
      status: status.dataset.status,
      count: Number(status.dataset.sourceCount) || 0,
      retrievedAt: status.dataset.sourceRetrievedAt || "",
      snapshot: status.dataset.sourceSha256 || ""
    };
  });

  const savedLanguage = localStorage.getItem("ocha-language");
  let language = translations[savedLanguage] ? savedLanguage : document.documentElement.lang || "en";
  let exercise = null;
  let editingEntityId = null;
  let isScreening = false;
  let previewPrepared = false;

  function translate(key, values = {}) {
    const text = translations[language][key] || translations.en[key] || key;
    return text.replace(/\{(\w+)\}/g, (match, name) =>
      values[name] === undefined ? match : values[name]
    );
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
    document.querySelectorAll("[data-language]").forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.language === language));
    });
    saveEntityButton.textContent = translate(editingEntityId ? "saveEntity" : "addEntity");
    if (exercise) renderEntityList();
    if (exercise?.screening) {
      renderScreeningResults();
      if (previewPrepared) renderPreview();
    }
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

  function formatDate(value) {
    if (!value) return translate("notSpecified");
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toISOString();
  }

  function makeId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function categoryLabel(category) {
    const keys = {
      subpartner: "categorySubpartner",
      vendor: "categoryVendor",
      contractor: "categoryContractor",
      other: "categoryOther"
    };
    return translate(keys[category] || "categoryOther");
  }

  function sourceLabel(source) {
    return translations[language][source.titleKey] || source.title;
  }

  function clearEntityForm() {
    editingEntityId = null;
    entityForm.reset();
    saveEntityButton.textContent = translate("addEntity");
    saveEntityButton.dataset.i18n = "addEntity";
    cancelEditButton.hidden = true;
  }

  function populateRequestForm(request) {
    document.querySelector("#cert-organisation").value = request?.organisation || "";
    document.querySelector("#cert-screened-by").value = request?.screenedBy || "";
    document.querySelector("#cert-role").value = request?.role || "";
    document.querySelector("#cert-user-email").value = request?.email || "";
  }

  function renderEntityList() {
    if (!exercise) return;
    if (!exercise.entities.length) {
      entityList.innerHTML = `<p class="certification-empty">${escapeHtml(translate("entityListEmpty"))}</p>`;
      return;
    }
    const categories = ["subpartner", "vendor", "contractor", "other"];
    entityList.innerHTML = categories.map(category => {
      const members = exercise.entities.filter(entity => entity.category === category);
      if (!members.length) return "";
      return `<div class="certification-entity-group"><h4>${escapeHtml(categoryLabel(category))} <span>${formatNumber(members.length)}</span></h4><ul>${members.map(entity => {
        const detail = [entity.country, entity.identifiers].filter(Boolean).join(" · ");
        const actions = exercise.screening
          ? ""
          : `<div class="certification-entity-actions"><button type="button" class="reset-button" data-entity-action="edit" data-entity-id="${escapeHtml(entity.id)}">${escapeHtml(translate("editEntity"))}</button><button type="button" class="reset-button" data-entity-action="remove" data-entity-id="${escapeHtml(entity.id)}">${escapeHtml(translate("removeEntity"))}</button></div>`;
        return `<li><div><strong>${escapeHtml(entity.name)}</strong>${detail ? `<small>${escapeHtml(detail)}</small>` : ""}${entity.aliases.length ? `<small>${escapeHtml(entity.aliases.join(" · "))}</small>` : ""}</div>${actions}</li>`;
      }).join("")}</ul></div>`;
    }).join("");
    const entityCount = translate("entityCount", { count: formatNumber(exercise.entities.length) });
    document.querySelector("#certification-exercise-meta").textContent =
      `${translate("exerciseMeta", { id: exercise.id, date: formatDate(exercise.createdAt) })} · ${entityCount}`;
  }

  function startEditing(entity) {
    editingEntityId = entity.id;
    entityNameInput.value = entity.name;
    entityCategoryInput.value = entity.category;
    entityCountryInput.value = entity.country;
    entityIdentifiersInput.value = entity.identifiers;
    entityAliasesInput.value = entity.aliases.join("\n");
    saveEntityButton.textContent = translate("saveEntity");
    saveEntityButton.dataset.i18n = "saveEntity";
    cancelEditButton.hidden = false;
    entityNameInput.focus();
  }

  function recordSourceUnavailable(source) {
    return source.count <= 0;
  }

  function summarizeScreening() {
    const entityRuns = exercise.screening.entities;
    const sourcesSearched = sources.filter(source =>
      !recordSourceUnavailable(source) &&
      entityRuns.length > 0 &&
      entityRuns.every(entity => entity.sources[source.key]?.status === "searched")
    ).length;
    const findings = entityRuns.reduce((sum, entity) => sum + entity.findings.length, 0);
    const entitiesWithFindings = entityRuns.filter(entity => entity.findings.length > 0).length;
    const entitiesWithoutFindings = entityRuns.filter(entity =>
      entity.findings.length === 0 && !entity.incomplete
    ).length;
    const incompleteEntities = entityRuns.filter(entity => entity.incomplete).length;
    const failedQueries = Object.values(exercise.screening.sourceRuns)
      .reduce((sum, run) => sum + run.failedQueries, 0);
    return {
      totalEntities: entityRuns.length,
      sourcesSearched,
      findings,
      entitiesWithFindings,
      entitiesWithoutFindings,
      incompleteEntities,
      queries: exercise.screening.queryCount,
      failedQueries
    };
  }

  function sourceStatusLabel(source, sourceRun) {
    if (recordSourceUnavailable(source)) {
      return source.status === "NOT_CONFIGURED"
        ? translate("databaseNotConfigured")
        : translate("databaseUnavailable");
    }
    if (!sourceRun || sourceRun.queries === 0) return translate("databaseUnavailable");
    if (sourceRun.failedQueries > 0 && sourceRun.successfulQueries > 0) {
      return translate("databasePartiallySearched");
    }
    if (sourceRun.failedQueries > 0) return translate("databaseSearchFailed");
    if (source.status === "NOT_CONFIGURED") {
      return translate("databaseSearchedPreviousSnapshot");
    }
    if (source.status !== "OK") return translate("databaseSearchedStaleSnapshot");
    return translate("databaseSearched");
  }

  function renderScreeningResults() {
    if (!exercise?.screening) return;
    const summary = summarizeScreening();
    const summaryItems = [
      ["totalEntities", summary.totalEntities],
      ["successfulSources", summary.sourcesSearched],
      ["potentialFindings", summary.findings],
      ["entitiesReview", summary.entitiesWithFindings],
      ["entitiesNoMatch", summary.entitiesWithoutFindings],
      ["incompleteSearches", summary.incompleteEntities],
      ["searchQueries", summary.queries]
    ];
    const sourceRows = sources.map(source => {
      const run = exercise.screening.sourceRuns[source.key];
      const sourceStatus = sourceStatusLabel(source, run);
      const retrieved = source.retrievedAt ? formatDate(source.retrievedAt) : translate("notRefreshedYet");
      const snapshot = source.snapshot || translate("notSpecified");
      const sourceCount = Number.isFinite(source.count) ? formatNumber(source.count) : "0";
      return `<tr><th scope="row">${escapeHtml(sourceLabel(source))}</th><td>${escapeHtml(sourceCount)}</td><td>${escapeHtml(retrieved)}</td><td class="snapshot-cell">${escapeHtml(snapshot)}</td><td>${escapeHtml(sourceStatus)}</td></tr>`;
    }).join("");
    const entityCards = exercise.screening.entities.map(entity => {
      const status = entity.findings.length ? translate("statusPotentialMatch")
        : entity.incomplete ? translate("statusPartialCoverage")
          : translate("statusNoPotentialMatch");
      const statusClass = entity.findings.length ? "review" : entity.incomplete ? "incomplete" : "no-match";
      const coverageGaps = sources.filter(source =>
        entity.sources[source.key]?.status !== "searched"
      ).map(sourceLabel).join(", ");
      const queryList = entity.queryLog.map(query => {
        const queryName = translations[language][`sourceShort_${query.source}`] || query.source;
        const queryError = query.error
          ? ` · ${escapeHtml(translate("queryError"))}: ${escapeHtml(query.error)}`
          : "";
        return `<li>${escapeHtml(query.name)} — ${escapeHtml(queryName)} · ${escapeHtml(formatDate(query.timestampUtc))}${queryError}</li>`;
      }).join("");
      const findingContent = entity.findings.length
        ? `<p class="certification-result-notice review">${escapeHtml(translate("findingsForEntity", { count: formatNumber(entity.findings.length) }))}</p><div class="certification-findings">${entity.findings.map(finding => {
          const href = safeSourceUrl(finding.source_url);
          const sourceName = translations[language][`sourceShort_${finding.source}`] || finding.source;
          const matchLabel = finding.match_type === "fuzzy"
            ? `<p class="fuzzy-result-label">${escapeHtml(translate("fuzzyMatchResult", { score: formatNumber(finding.match_score) }))}</p>`
            : finding.match_type === "exact"
              ? `<p class="fuzzy-result-label">${escapeHtml(translate("exactMatchResult"))}</p>`
              : "";
          return `<article><h5>${escapeHtml(finding.name || translate("notSpecified"))}</h5>${matchLabel}<dl><dt>${escapeHtml(translate("resultSource"))}</dt><dd>${escapeHtml(sourceName)}</dd><dt>${escapeHtml(translate("resultCountry"))}</dt><dd>${escapeHtml(finding.country || translate("notSpecified"))}</dd><dt>${escapeHtml(translate("resultAliases"))}</dt><dd>${escapeHtml(finding.aliases || translate("noneShown"))}</dd><dt>${escapeHtml(translate("resultReference"))}</dt><dd>${escapeHtml(finding.source_ref || translate("notSpecified"))}</dd></dl><a href="${escapeHtml(href)}" target="_blank" rel="noopener">${escapeHtml(translate("openOfficialSource"))} ↗</a></article>`;
        }).join("")}</div>`
        : `<p class="certification-result-notice no-match">${escapeHtml(translate("noFindingsForEntity"))}</p>`;
      const incompleteNotice = entity.incomplete
        ? `<p class="certification-result-notice incomplete">${escapeHtml(translate("incompleteEntityNotice", { sources: coverageGaps }))}</p>`
        : "";
      return `<details class="certification-entity-result"><summary><span>${escapeHtml(entity.entity.name)}</span><span class="certification-result-status ${statusClass}">${escapeHtml(status)}</span></summary><p>${escapeHtml(categoryLabel(entity.entity.category))}${entity.entity.country ? ` · ${escapeHtml(entity.entity.country)}` : ""} · ${escapeHtml(translate("screeningTimestamp", { date: formatDate(entity.completedAt) }))}</p><p><strong>${escapeHtml(translate("searchedNameQueries"))}:</strong> ${escapeHtml(entity.queries.join(" · "))}</p><p><strong>${escapeHtml(translate("queryDetails"))}:</strong></p><ul class="certification-query-list">${queryList}</ul>${incompleteNotice}${findingContent}</details>`;
    }).join("");
    resultsPanel.innerHTML = `<div class="certification-summary">${summaryItems.map(([key, value]) => `<div><span>${escapeHtml(translate(key))}</span><strong>${escapeHtml(formatNumber(value))}</strong></div>`).join("")}</div><h4>${escapeHtml(translate("sourceRegister"))}</h4><div class="certification-table-wrap"><table class="certification-table"><thead><tr><th>${escapeHtml(translate("sourceName"))}</th><th>${escapeHtml(translate("sourceRecords"))}</th><th>${escapeHtml(translate("sourceRetrieved"))}</th><th>${escapeHtml(translate("sourceSnapshot"))}</th><th>${escapeHtml(translate("sourceSearchStatus"))}</th></tr></thead><tbody>${sourceRows}</tbody></table></div><h4>${escapeHtml(translate("entityResults"))}</h4><div class="certification-result-list">${entityCards}</div>`;
    resultsPanel.hidden = false;
  }

  function safeSourceUrl(value) {
    try {
      const url = new URL(String(value));
      return url.protocol === "https:" ? url.href : "#";
    } catch {
      return "#";
    }
  }

  function renderPreview() {
    if (!exercise?.screening) return;
    const summary = summarizeScreening();
    const sourceRows = sources.map(source => {
      const sourceRun = exercise.screening.sourceRuns[source.key];
      return `<tr><th scope="row">${escapeHtml(sourceLabel(source))}</th><td>${escapeHtml(formatNumber(source.count))}</td><td>${escapeHtml(source.retrievedAt ? formatDate(source.retrievedAt) : translate("notRefreshedYet"))}</td><td class="snapshot-cell">${escapeHtml(source.snapshot || translate("notSpecified"))}</td><td>${escapeHtml(sourceStatusLabel(source, sourceRun))}</td></tr>`;
    }).join("");
    const entityRows = exercise.screening.entities.map(result => {
      const status = result.findings.length ? translate("statusPotentialMatch")
        : result.incomplete ? translate("statusPartialCoverage")
          : translate("statusNoPotentialMatch");
      const searchedSources = sources.filter(source =>
        result.sources[source.key]?.status === "searched"
      ).map(sourceLabel).join(", ") || translate("notSpecified");
      const findingDetails = result.findings.length
        ? `<ul>${result.findings.map(finding => {
          const matchLabel = finding.match_type === "fuzzy"
            ? ` · ${translate("fuzzyMatchResult", { score: formatNumber(finding.match_score) })}`
            : "";
          return `<li>${escapeHtml(finding.name || translate("notSpecified"))} — ${escapeHtml(translations[language][`sourceShort_${finding.source}`] || finding.source)} · ${escapeHtml(finding.source_ref || translate("notSpecified"))}${escapeHtml(matchLabel)}</li>`;
        }).join("")}</ul>`
        : escapeHtml(translate("noMatchingRecords"));
      return `<tr><td>${escapeHtml(categoryLabel(result.entity.category))}</td><td>${escapeHtml(result.entity.name)}${result.entity.aliases.length ? `<small>${escapeHtml(result.entity.aliases.join(" · "))}</small>` : ""}<small>${escapeHtml(translate("searchedNameQueries"))}: ${escapeHtml(result.queries.join(" · "))}</small></td><td>${escapeHtml(result.entity.country || translate("notSpecified"))}</td><td>${escapeHtml(result.entity.identifiers || translate("notSpecified"))}</td><td>${escapeHtml(searchedSources)}</td><td>${escapeHtml(formatNumber(result.findings.length))}</td><td>${findingDetails}</td><td>${escapeHtml(status)}</td><td>${escapeHtml(formatDate(result.completedAt))}</td></tr>`;
    }).join("");
    const requestRows = [
      ["requestingOrganisation", exercise.request.organisation],
      ["screenedBy", exercise.request.screenedBy],
      ["organisationRole", exercise.request.role],
      ["userEmail", exercise.request.email],
      ["screeningTimestampLabel", formatDate(exercise.screening.completedAt)],
      ["previewGenerated", formatDate(new Date().toISOString())]
    ];
    const previewDate = requestRows.pop()[1];
    previewPanel.innerHTML = `
      <div class="certification-preview-banner">${escapeHtml(translate("previewWarning"))}</div>
      <h3>${escapeHtml(translate("previewTitle"))}</h3>
      <p>${escapeHtml(translate("previewNotSigned"))}</p>
      <p><strong>${escapeHtml(translate("exerciseIdLabel"))}:</strong> ${escapeHtml(exercise.id)}</p>
      <h4>${escapeHtml(translate("searchRequest"))}</h4>
      <dl>${requestRows.map(([key, value]) => `<dt>${escapeHtml(translate(key))}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl>
      <h4>${escapeHtml(translate("previewScreening"))}</h4>
      <p>${escapeHtml(translate("totalEntities"))}: ${escapeHtml(formatNumber(summary.totalEntities))} · ${escapeHtml(translate("successfulSources"))}: ${escapeHtml(formatNumber(summary.sourcesSearched))} · ${escapeHtml(translate("potentialFindings"))}: ${escapeHtml(formatNumber(summary.findings))} · ${escapeHtml(translate("incompleteSearches"))}: ${escapeHtml(formatNumber(summary.incompleteEntities))}</p>
      <p>${escapeHtml(translate("fuzzyMatching"))}: ${escapeHtml(translate(exercise.screening.fuzzyMatching ? "fuzzyEnabled" : "fuzzyDisabled"))}</p>
      <h4>${escapeHtml(translate("sourceRegister"))}</h4>
      <div class="certification-table-wrap"><table class="certification-table"><thead><tr><th>${escapeHtml(translate("sourceName"))}</th><th>${escapeHtml(translate("sourceRecords"))}</th><th>${escapeHtml(translate("sourceRetrieved"))}</th><th>${escapeHtml(translate("sourceSnapshot"))}</th><th>${escapeHtml(translate("sourceSearchStatus"))}</th></tr></thead><tbody>${sourceRows}</tbody></table></div>
      <h4>${escapeHtml(translate("previewThirdParties"))}</h4>
      <div class="certification-table-wrap"><table class="certification-table certification-entity-table"><thead><tr><th>${escapeHtml(translate("entityCategory"))}</th><th>${escapeHtml(translate("entityName"))}</th><th>${escapeHtml(translate("entityCountry"))}</th><th>${escapeHtml(translate("entityIdentifiers"))}</th><th>${escapeHtml(translate("sourceName"))}</th><th>${escapeHtml(translate("potentialFindings"))}</th><th>${escapeHtml(translate("findingDetails"))}</th><th>${escapeHtml(translate("sourceSearchStatus"))}</th><th>${escapeHtml(translate("screeningTimestampLabel"))}</th></tr></thead><tbody>${entityRows}</tbody></table></div>
      <p>${escapeHtml(translate("previewGenerated", { date: previewDate }))}</p>
      <p class="certification-result-notice incomplete">${escapeHtml(translate("screeningNoticeText"))}</p>
      <button id="export-certification-pdf" class="no-print" type="button">${escapeHtml(translate("pdfExport"))}</button>
      <p class="pdf-export-hint no-print">${escapeHtml(translate("pdfExportHint"))}</p>`;
    previewPanel.querySelector("#export-certification-pdf")
      .addEventListener("click", () => window.print());
    previewPanel.hidden = false;
    previewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function formatNumber(value) {
    return new Intl.NumberFormat(language).format(Number(value) || 0);
  }

  function setControlsDisabled(container, disabled) {
    container.querySelectorAll("input, select, textarea, button").forEach(control => {
      control.disabled = disabled;
    });
  }

  function clearScreeningState() {
    exercise.screening = null;
    resultsPanel.innerHTML = "";
    resultsPanel.hidden = true;
    reviewPanel.hidden = true;
    previewPanel.innerHTML = "";
    previewPanel.hidden = true;
    acknowledgement.checked = false;
    previewButton.disabled = true;
    previewPrepared = false;
  }

  function resetReport() {
    exercise = null;
    editingEntityId = null;
    isScreening = false;
    previewPrepared = false;
    requestForm.reset();
    setControlsDisabled(requestForm, false);
    createRequestButton.hidden = false;
    createRequestButton.textContent = translate("registerSearch");
    createRequestButton.dataset.i18n = "registerSearch";
    editRequestButton.hidden = true;
    editRequestButton.disabled = true;
    setControlsDisabled(entityForm, false);
    screeningButton.disabled = false;
    newReportButton.disabled = false;
    fuzzyMatchingInput.checked = false;
    entityWorkflow.hidden = true;
    entityList.innerHTML = "";
    resultsPanel.innerHTML = "";
    resultsPanel.hidden = true;
    reviewPanel.hidden = true;
    previewPanel.innerHTML = "";
    previewPanel.hidden = true;
    screeningStatus.textContent = "";
    clearEntityForm();
    document.querySelector("#cert-organisation").focus();
  }

  requestForm.addEventListener("submit", event => {
    event.preventDefault();
    if (!requestForm.reportValidity()) return;
    const request = {
      organisation: document.querySelector("#cert-organisation").value.trim(),
      screenedBy: document.querySelector("#cert-screened-by").value.trim(),
      role: document.querySelector("#cert-role").value.trim(),
      email: document.querySelector("#cert-user-email").value.trim()
    };
    if (!exercise) {
      exercise = {
        id: makeId(),
        createdAt: new Date().toISOString(),
        request,
        entities: [],
        screening: null
      };
    } else {
      exercise.request = request;
    }
    previewPrepared = false;
    requestForm.querySelectorAll("input, button").forEach(control => {
      control.disabled = true;
    });
    createRequestButton.hidden = true;
    editRequestButton.hidden = false;
    editRequestButton.disabled = false;
    if (exercise.screening) {
      clearScreeningState();
      setControlsDisabled(requestForm, true);
      setControlsDisabled(entityForm, false);
      screeningButton.disabled = false;
      fuzzyMatchingInput.disabled = false;
      newReportButton.disabled = false;
      screeningStatus.textContent = translate("requestUpdated");
    } else {
      screeningStatus.textContent = translate("exerciseRegistered");
    }
    entityWorkflow.hidden = false;
    renderEntityList();
    if (!exercise.screening) entityNameInput.focus();
  });

  editRequestButton.addEventListener("click", () => {
    if (!exercise) return;
    setControlsDisabled(requestForm, false);
    createRequestButton.hidden = false;
    createRequestButton.disabled = false;
    createRequestButton.textContent = translate("saveRequest");
    createRequestButton.dataset.i18n = "saveRequest";
    editRequestButton.hidden = true;
    document.querySelector("#cert-organisation").focus();
  });

  resetRequestButton.addEventListener("click", () => {
    populateRequestForm(exercise?.request);
    if (!exercise) {
      requestForm.reset();
    }
    createRequestButton.textContent = translate("registerSearch");
    createRequestButton.dataset.i18n = "registerSearch";
    if (exercise) {
      setControlsDisabled(requestForm, true);
      editRequestButton.hidden = false;
      editRequestButton.disabled = false;
      resetRequestButton.disabled = true;
    }
    document.querySelector("#cert-organisation").focus();
  });

  entityForm.addEventListener("submit", event => {
    event.preventDefault();
    if (!entityForm.reportValidity()) return;
    const name = entityNameInput.value.trim();
    if (!name) {
      screeningStatus.textContent = translate("entityNameRequired");
      return;
    }
    const entityData = {
      name,
      category: entityCategoryInput.value,
      country: entityCountryInput.value.trim(),
      identifiers: entityIdentifiersInput.value.trim(),
      aliases: Array.from(new Set(
        entityAliasesInput.value.split(/\r?\n/).map(alias => alias.trim()).filter(Boolean)
      ))
    };
    if ([entityData.name, ...entityData.aliases].some(term => term.length < 2)) {
      screeningStatus.textContent = translate("entityNameMinimum");
      return;
    }
    if (editingEntityId) {
      exercise.entities = exercise.entities.map(entity =>
        entity.id === editingEntityId ? { ...entity, ...entityData } : entity
      );
      screeningStatus.textContent = translate("entityUpdated");
    } else {
      exercise.entities.push({ id: makeId(), ...entityData });
      screeningStatus.textContent = translate("entityAdded");
    }
    clearEntityForm();
    renderEntityList();
    entityNameInput.focus();
  });

  cancelEditButton.addEventListener("click", () => {
    clearEntityForm();
    entityNameInput.focus();
  });

  resetEntityButton.addEventListener("click", () => {
    clearEntityForm();
    entityNameInput.focus();
  });

  entityList.addEventListener("click", event => {
    const button = event.target.closest("[data-entity-action]");
    if (!button || !exercise || exercise.screening) return;
    const entity = exercise.entities.find(item => item.id === button.dataset.entityId);
    if (!entity) return;
    if (button.dataset.entityAction === "edit") {
      startEditing(entity);
      return;
    }
    if (button.dataset.entityAction === "remove" && window.confirm(translate("confirmRemoveEntity"))) {
      exercise.entities = exercise.entities.filter(item => item.id !== entity.id);
      if (editingEntityId === entity.id) clearEntityForm();
      renderEntityList();
    }
  });

  async function searchSourceForName(source, name, fuzzyMatching) {
    const params = new URLSearchParams({
      name,
      source: source.key,
      page_size: "all",
      page: "1",
      fuzzy_match: String(fuzzyMatching)
    });
    const response = await fetch(`/api/search?${params.toString()}`);
    const body = await response.json();
    if (!response.ok || body.error) {
      throw new Error(body.error || `${translate("databaseSearchFailed")} (${response.status})`);
    }
    return body.results;
  }

  async function runScreening() {
    if (!exercise || isScreening) return;
    if (!exercise.entities.length) {
      screeningStatus.textContent = translate("entityListEmpty");
      return;
    }
    isScreening = true;
    screeningButton.disabled = true;
    newReportButton.disabled = true;
    screeningStatus.textContent = translate("screeningStarting");
    previewPrepared = false;
    resultsPanel.hidden = true;
    reviewPanel.hidden = true;
    previewPanel.hidden = true;
    acknowledgement.checked = false;
    previewButton.disabled = true;
    const screening = {
      startedAt: new Date().toISOString(),
      completedAt: "",
      fuzzyMatching: fuzzyMatchingInput.checked,
      entities: [],
      queryCount: 0,
      sourceRuns: Object.fromEntries(sources.map(source => [
        source.key,
        { queries: 0, successfulQueries: 0, failedQueries: 0 }
      ]))
    };
    try {
      for (let index = 0; index < exercise.entities.length; index++) {
        const entity = exercise.entities[index];
        screeningStatus.textContent = translate("screeningProgress", {
          current: formatNumber(index + 1),
          total: formatNumber(exercise.entities.length),
          entity: entity.name
        });
        const terms = Array.from(new Set(
          [entity.name, ...entity.aliases].map(term => term.trim()).filter(Boolean)
        ));
        const entityRun = {
          entity: { ...entity },
          startedAt: new Date().toISOString(),
          completedAt: "",
          queries: terms,
          queryLog: [],
          sources: {},
          unavailableSources: [],
          failedSources: [],
          findings: [],
          incomplete: false
        };
        const findingKeys = new Set();
        for (const source of sources) {
          if (recordSourceUnavailable(source)) {
            entityRun.sources[source.key] = { status: "unavailable", queries: 0 };
            entityRun.unavailableSources.push(source.key);
            entityRun.incomplete = true;
            continue;
          }
          const sourceRun = screening.sourceRuns[source.key];
          let failedQueries = 0;
          let successfulQueries = 0;
          for (const term of terms) {
            screening.queryCount++;
            sourceRun.queries++;
            const queryTimestamp = new Date().toISOString();
            try {
              const results = await searchSourceForName(
                source,
                term,
                screening.fuzzyMatching
              );
              successfulQueries++;
              sourceRun.successfulQueries++;
              entityRun.queryLog.push({
                name: term,
                source: source.key,
                parameters: {
                  name: term,
                  source: source.key,
                  page_size: "all",
                  page: 1,
                  fuzzy_match: screening.fuzzyMatching
                },
                timestampUtc: queryTimestamp,
                status: "searched"
              });
              results.forEach(result => {
                const identity = result.source_ref
                  ? `${result.source}:${result.source_ref}`
                  : `${result.source}:${result.id}`;
                if (!findingKeys.has(identity)) {
                  findingKeys.add(identity);
                  entityRun.findings.push(result);
                }
              });
            } catch (error) {
              failedQueries++;
              sourceRun.failedQueries++;
              entityRun.queryLog.push({
                name: term,
                source: source.key,
                parameters: {
                  name: term,
                  source: source.key,
                  page_size: "all",
                  page: 1,
                  fuzzy_match: screening.fuzzyMatching
                },
                timestampUtc: queryTimestamp,
                status: "error",
                error: error instanceof Error ? error.message : String(error)
              });
            }
          }
          entityRun.sources[source.key] = {
            status: failedQueries === 0 ? "searched"
              : successfulQueries > 0 ? "partial" : "error",
            queries: terms.length,
            failedQueries
          };
          if (failedQueries > 0) {
            entityRun.failedSources.push(source.key);
            entityRun.incomplete = true;
          }
        }
        entityRun.completedAt = new Date().toISOString();
        screening.entities.push(entityRun);
      }
      screening.completedAt = new Date().toISOString();
      exercise.screening = screening;
      renderEntityList();
      renderScreeningResults();
      reviewPanel.hidden = false;
      screeningStatus.textContent = summarizeScreening().sourcesSearched > 0
        ? translate("screeningComplete")
        : translate("screeningNoResults");
      setControlsDisabled(requestForm, true);
      setControlsDisabled(entityForm, true);
      screeningButton.disabled = true;
      fuzzyMatchingInput.disabled = true;
      newReportButton.disabled = false;
    } catch (error) {
      screeningStatus.textContent = translate("screeningFailed", {
        error: error instanceof Error ? error.message : String(error)
      });
    } finally {
      isScreening = false;
      if (!exercise?.screening) {
        screeningButton.disabled = false;
        newReportButton.disabled = false;
      }
    }
  }

  screeningButton.addEventListener("click", runScreening);
  acknowledgement.addEventListener("change", () => {
    previewButton.disabled = !acknowledgement.checked;
  });
  previewButton.addEventListener("click", () => {
    if (!acknowledgement.checked) {
      screeningStatus.textContent = translate("reviewRequired");
      return;
    }
    previewPrepared = true;
    renderPreview();
  });

  newReportButton.addEventListener("click", () => {
    if (!window.confirm(translate("confirmNewExercise"))) return;
    resetReport();
  });

  document.querySelectorAll("[data-language]").forEach(button => {
    button.addEventListener("click", () => {
      localStorage.setItem("ocha-language", button.dataset.language);
      applyLanguage(button.dataset.language);
    });
  });

  applyLanguage(language);

})();
