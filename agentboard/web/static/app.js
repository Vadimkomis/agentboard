(function (root, factory) {
  var helpers = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = helpers;
  }
  if (root && root.document) {
    root.AgentBoard = helpers;
    helpers.start(root.document, root);
  }
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var THEME_KEY = "agentboard-theme";
  var THEMES = ["dark", "light"];

  function normalizeTheme(value, prefersLight) {
    if (THEMES.indexOf(value) !== -1) {
      return value;
    }
    return prefersLight ? "light" : "dark";
  }

  function readTheme(storage, mediaQuery) {
    var saved = null;
    try {
      saved = storage && storage.getItem(THEME_KEY);
    } catch (_) {
      saved = null;
    }
    return normalizeTheme(saved, Boolean(mediaQuery && mediaQuery.matches));
  }

  function applyTheme(documentElement, theme) {
    var normalized = normalizeTheme(theme, false);
    documentElement.dataset.theme = normalized;
    return normalized;
  }

  function toggleTheme(current) {
    return normalizeTheme(current, false) === "dark" ? "light" : "dark";
  }

  function persistTheme(storage, theme) {
    try {
      storage.setItem(THEME_KEY, theme);
      return true;
    } catch (_) {
      return false;
    }
  }

  function reorderKeys(keys, movedKey, targetKey, placeAfter) {
    var next = keys.slice();
    var movedIndex = next.indexOf(movedKey);
    var targetIndex = next.indexOf(targetKey);
    if (movedIndex < 0 || targetIndex < 0 || movedKey === targetKey) {
      return next;
    }
    next.splice(movedIndex, 1);
    targetIndex = next.indexOf(targetKey);
    next.splice(targetIndex + (placeAfter ? 1 : 0), 0, movedKey);
    return next;
  }

  function moveKey(keys, movedKey, direction) {
    var index = keys.indexOf(movedKey);
    var target = index + direction;
    if (index < 0 || target < 0 || target >= keys.length) {
      return keys.slice();
    }
    var next = keys.slice();
    next.splice(index, 1);
    next.splice(target, 0, movedKey);
    return next;
  }

  function trappedFocusIndex(currentIndex, count, backward) {
    if (count <= 0) {
      return -1;
    }
    if (currentIndex < 0) {
      return backward ? count - 1 : 0;
    }
    if (backward && currentIndex === 0) {
      return count - 1;
    }
    if (!backward && currentIndex === count - 1) {
      return 0;
    }
    return currentIndex + (backward ? -1 : 1);
  }

  function rowsFor(list) {
    return Array.prototype.slice.call(list.querySelectorAll(":scope > [data-feature-id]"));
  }

  function rowIds(list) {
    return rowsFor(list).map(function (row) {
      return row.dataset.featureId;
    });
  }

  function renderOrder(list, ids) {
    var rows = rowsFor(list);
    var byId = {};
    rows.forEach(function (row) {
      byId[row.dataset.featureId] = row;
    });
    ids.forEach(function (id) {
      if (byId[id]) {
        list.appendChild(byId[id]);
      }
    });
  }

  function syncFeatureInputs(form, ids) {
    var container = form.querySelector("[data-feature-id-inputs]");
    if (!container) {
      return;
    }
    container.textContent = "";
    var input = form.ownerDocument.createElement("input");
    input.type = "hidden";
    input.name = "feature_ids";
    input.value = ids.join(",");
    container.appendChild(input);
  }

  function announce(form, message) {
    var status = form.querySelector("[data-reorder-status]");
    if (status) {
      status.textContent = message;
    }
  }

  function submitOrder(form, list, focusedId) {
    var ids = rowIds(list);
    syncFeatureInputs(form, ids);
    announce(form, "Saving backlog order…");
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
    if (focusedId) {
      var moved = list.querySelector('[data-feature-id="' + focusedId + '"] [data-move]');
      if (moved) {
        moved.focus();
      }
    }
  }

  function setupReorder(form) {
    if (form.dataset.reorderEnabled !== "true") {
      return;
    }
    var list = form.querySelector("[data-reorder-list]");
    var draggedId = null;
    if (!list) {
      return;
    }

    list.addEventListener("click", function (event) {
      var button = event.target.closest("[data-move]");
      var row = event.target.closest("[data-feature-id]");
      if (!button || !row) {
        return;
      }
      event.preventDefault();
      var direction = button.dataset.move === "up" ? -1 : 1;
      var current = rowIds(list);
      var next = moveKey(current, row.dataset.featureId, direction);
      if (next.join(",") === current.join(",")) {
        announce(form, "That feature is already at the edge of the backlog.");
        return;
      }
      renderOrder(list, next);
      submitOrder(form, list, row.dataset.featureId);
    });

    list.addEventListener("dragstart", function (event) {
      var row = event.target.closest("[data-feature-id]");
      if (!row) {
        return;
      }
      draggedId = row.dataset.featureId;
      row.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", draggedId);
    });

    list.addEventListener("dragover", function (event) {
      var row = event.target.closest("[data-feature-id]");
      if (!row || row.dataset.featureId === draggedId) {
        return;
      }
      event.preventDefault();
      rowsFor(list).forEach(function (item) {
        item.classList.remove("is-drop-target");
      });
      row.classList.add("is-drop-target");
    });

    list.addEventListener("drop", function (event) {
      var target = event.target.closest("[data-feature-id]");
      if (!target || !draggedId || target.dataset.featureId === draggedId) {
        return;
      }
      event.preventDefault();
      var rectangle = target.getBoundingClientRect();
      var after = event.clientY > rectangle.top + rectangle.height / 2;
      var next = reorderKeys(rowIds(list), draggedId, target.dataset.featureId, after);
      renderOrder(list, next);
      submitOrder(form, list, draggedId);
    });

    list.addEventListener("dragend", function () {
      rowsFor(list).forEach(function (row) {
        row.classList.remove("is-dragging", "is-drop-target");
      });
      draggedId = null;
    });
  }

  function setInteractiveRegion(element, isInteractive) {
    if (!element) {
      return;
    }
    element.toggleAttribute("inert", !isInteractive);
    if (isInteractive) {
      element.removeAttribute("aria-hidden");
    } else {
      element.setAttribute("aria-hidden", "true");
    }
  }

  function navigationFocusables(sidebar) {
    var selector = [
      "a[href]",
      "button:not([disabled])",
      "input:not([disabled]):not([type='hidden'])",
      "select:not([disabled])",
      "textarea:not([disabled])",
      "[tabindex]:not([tabindex='-1'])"
    ].join(",");
    return Array.prototype.slice.call(sidebar.querySelectorAll(selector)).filter(
      function (element) {
        return !element.hidden && element.getAttribute("aria-hidden") !== "true";
      }
    );
  }

  function setupNavigation(document, windowObject) {
    var shell = document.querySelector("[data-app-shell]");
    var open = document.querySelector("[data-nav-open]");
    var sidebar = document.querySelector("#primary-navigation");
    var workspace = shell && shell.querySelector(".workspace");
    var media = windowObject.matchMedia
      ? windowObject.matchMedia("(max-width: 960px)")
      : { matches: false };
    if (!shell || !open || !sidebar || !workspace) {
      return;
    }

    function setOpen(shouldOpen, restoreFocus) {
      var isOpen = Boolean(shouldOpen && media.matches);
      shell.dataset.navOpened = String(isOpen);
      open.setAttribute("aria-expanded", String(isOpen));
      document.body.style.overflow = isOpen ? "hidden" : "";
      if (isOpen) {
        setInteractiveRegion(sidebar, true);
        var focusables = navigationFocusables(sidebar);
        if (focusables.length) {
          focusables[0].focus();
        }
        setInteractiveRegion(workspace, false);
      } else {
        setInteractiveRegion(workspace, true);
        if (restoreFocus && media.matches) {
          open.focus();
        }
        setInteractiveRegion(sidebar, !media.matches);
      }
    }

    function trapFocus(event) {
      if (event.key !== "Tab" || shell.dataset.navOpened !== "true") {
        return;
      }
      var focusables = navigationFocusables(sidebar);
      var currentIndex = focusables.indexOf(document.activeElement);
      var nextIndex = trappedFocusIndex(currentIndex, focusables.length, event.shiftKey);
      if (nextIndex >= 0) {
        event.preventDefault();
        focusables[nextIndex].focus();
      }
    }

    function respondToViewport() {
      setOpen(false, false);
    }

    open.addEventListener("click", function () {
      setOpen(true, false);
    });
    document.querySelectorAll("[data-nav-close]").forEach(function (control) {
      control.addEventListener("click", function () {
        setOpen(false, true);
      });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && shell.dataset.navOpened === "true") {
        setOpen(false, true);
      }
      trapFocus(event);
    });
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", respondToViewport);
    } else if (typeof media.addListener === "function") {
      media.addListener(respondToViewport);
    }
    respondToViewport();
  }

  function setupTheme(document, windowObject) {
    var media = windowObject.matchMedia
      ? windowObject.matchMedia("(prefers-color-scheme: light)")
      : { matches: false };
    var current = readTheme(windowObject.localStorage, media);
    applyTheme(document.documentElement, current);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        current = toggleTheme(document.documentElement.dataset.theme);
        applyTheme(document.documentElement, current);
        persistTheme(windowObject.localStorage, current);
        button.setAttribute(
          "aria-label",
          current === "dark" ? "Switch to light theme" : "Switch to dark theme"
        );
      });
    });
  }

  function start(document, windowObject) {
    setupTheme(document, windowObject);
    setupNavigation(document, windowObject);
    document.querySelectorAll("[data-reorder-form]").forEach(setupReorder);
  }

  return {
    THEME_KEY: THEME_KEY,
    normalizeTheme: normalizeTheme,
    readTheme: readTheme,
    applyTheme: applyTheme,
    toggleTheme: toggleTheme,
    persistTheme: persistTheme,
    reorderKeys: reorderKeys,
    moveKey: moveKey,
    trappedFocusIndex: trappedFocusIndex,
    setupNavigation: setupNavigation,
    start: start
  };
}));
