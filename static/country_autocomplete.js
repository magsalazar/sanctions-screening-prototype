(() => {
  function initialize(root = document) {
    const controls = Array.from(root.querySelectorAll(".country-control")).map(control => {
      const input = control.querySelector("[data-country-input]");
      const list = control.querySelector(".country-suggestions");
      const options = Array.from(list.querySelectorAll('[role="option"]'));
      let activeIndex = -1;

      function close() {
        list.hidden = true;
        input.setAttribute("aria-expanded", "false");
        input.removeAttribute("aria-activedescendant");
        activeIndex = -1;
      }

      function normalize(value) {
        return value.normalize("NFKD")
          .replace(/[\u0300-\u036f]/g, "")
          .toLocaleLowerCase()
          .replace(/[^a-z0-9]/g, "");
      }

      function update() {
        const prefix = normalize(input.value.trim());
        let shown = 0;
        options.forEach(option => {
          const aliases = (option.dataset.searchAliases || "").split("|").filter(Boolean);
          const matches = normalize(option.dataset.country).includes(prefix)
            || aliases.some(alias => normalize(alias).includes(prefix));
          const visible = matches && (prefix !== "" || shown < 8);
          option.hidden = !visible;
          option.setAttribute("aria-selected", "false");
          if (visible) shown++;
        });
        list.hidden = shown === 0;
        input.setAttribute("aria-expanded", String(shown > 0));
        input.removeAttribute("aria-activedescendant");
        activeIndex = -1;
      }

      function choose(option) {
        if (!option) return;
        input.value = option.dataset.country;
        close();
        input.focus();
      }

      function setActive(index) {
        const visibleOptions = options.filter(option => !option.hidden);
        if (!visibleOptions.length) return;
        activeIndex = (index + visibleOptions.length) % visibleOptions.length;
        options.forEach(option => option.setAttribute("aria-selected", "false"));
        const option = visibleOptions[activeIndex];
        option.setAttribute("aria-selected", "true");
        input.setAttribute("aria-activedescendant", option.id);
        option.scrollIntoView({ block: "nearest" });
      }

      input.addEventListener("focus", update);
      input.addEventListener("input", update);
      input.addEventListener("keydown", event => {
        if (event.key === "ArrowDown" && !list.hidden) {
          event.preventDefault();
          setActive(activeIndex + 1);
        } else if (event.key === "ArrowUp" && !list.hidden) {
          event.preventDefault();
          setActive(activeIndex < 0 ? -1 : activeIndex - 1);
        } else if (event.key === "Enter" && activeIndex >= 0) {
          event.preventDefault();
          choose(options.find(option => option.getAttribute("aria-selected") === "true"));
        } else if (event.key === "Escape") {
          close();
        }
      });
      input.addEventListener("blur", () => setTimeout(close, 0));
      list.addEventListener("pointerdown", event => {
        const option = event.target.closest('[role="option"]');
        if (!option) return;
        event.preventDefault();
        choose(option);
      });
      return { close };
    });

    document.addEventListener("pointerdown", event => {
      if (!event.target.closest(".country-control")) {
        controls.forEach(control => control.close());
      }
    });

    return {
      closeAll() {
        controls.forEach(control => control.close());
      }
    };
  }

  window.OCHACountryAutocomplete = { initialize };
})();
