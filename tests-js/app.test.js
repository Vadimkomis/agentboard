"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  THEME_KEY,
  normalizeTheme,
  readTheme,
  applyTheme,
  toggleTheme,
  persistTheme,
  reorderKeys,
  moveKey,
  trappedFocusIndex,
  setupNavigation
} = require("../agentboard/web/static/app.js");

test("theme helpers accept explicit themes and follow a system fallback", () => {
  assert.equal(normalizeTheme("dark", true), "dark");
  assert.equal(normalizeTheme("light", false), "light");
  assert.equal(normalizeTheme("unexpected", true), "light");
  assert.equal(normalizeTheme(null, false), "dark");
});

test("stored theme wins and inaccessible storage falls back safely", () => {
  const storage = { getItem: (key) => key === THEME_KEY ? "dark" : null };
  assert.equal(readTheme(storage, { matches: true }), "dark");
  assert.equal(readTheme({ getItem: () => { throw new Error("blocked"); } }, { matches: true }), "light");
});

test("theme can be applied, toggled, and persisted", () => {
  const root = { dataset: {} };
  const values = {};
  const storage = { setItem: (key, value) => { values[key] = value; } };

  assert.equal(applyTheme(root, "light"), "light");
  assert.equal(root.dataset.theme, "light");
  assert.equal(toggleTheme(root.dataset.theme), "dark");
  assert.equal(persistTheme(storage, "dark"), true);
  assert.equal(values[THEME_KEY], "dark");
  assert.equal(persistTheme({ setItem: () => { throw new Error("blocked"); } }, "light"), false);
});

test("drag reorder moves one key before or after the target without mutation", () => {
  const original = ["1", "2", "3", "4"];

  assert.deepEqual(reorderKeys(original, "1", "3", false), ["2", "1", "3", "4"]);
  assert.deepEqual(reorderKeys(original, "1", "3", true), ["2", "3", "1", "4"]);
  assert.deepEqual(original, ["1", "2", "3", "4"]);
});

test("drag reorder is stable for missing and identical keys", () => {
  assert.deepEqual(reorderKeys(["1", "2"], "missing", "2", false), ["1", "2"]);
  assert.deepEqual(reorderKeys(["1", "2"], "1", "1", true), ["1", "2"]);
});

test("keyboard reorder respects list edges", () => {
  assert.deepEqual(moveKey(["1", "2", "3"], "2", -1), ["2", "1", "3"]);
  assert.deepEqual(moveKey(["1", "2", "3"], "2", 1), ["1", "3", "2"]);
  assert.deepEqual(moveKey(["1", "2", "3"], "1", -1), ["1", "2", "3"]);
  assert.deepEqual(moveKey(["1", "2", "3"], "3", 1), ["1", "2", "3"]);
});

test("mobile navigation focus wraps inside the open drawer", () => {
  assert.equal(trappedFocusIndex(0, 4, true), 3);
  assert.equal(trappedFocusIndex(3, 4, false), 0);
  assert.equal(trappedFocusIndex(1, 4, false), 2);
  assert.equal(trappedFocusIndex(-1, 4, false), 0);
  assert.equal(trappedFocusIndex(-1, 4, true), 3);
  assert.equal(trappedFocusIndex(0, 0, false), -1);
});

function interactiveElement(document, extra = {}) {
  const listeners = {};
  const attributes = {};
  return Object.assign({
    hidden: false,
    listeners,
    addEventListener: (name, listener) => {
      listeners[name] = listener;
    },
    setAttribute: (name, value) => {
      attributes[name] = value;
    },
    getAttribute: (name) => attributes[name] ?? null,
    removeAttribute: (name) => {
      delete attributes[name];
    },
    toggleAttribute: (name, force) => {
      if (force) {
        attributes[name] = "";
      } else {
        delete attributes[name];
      }
    },
    focus() {
      document.activeElement = this;
    }
  }, extra);
}

test("mobile navigation isolates the drawer and restores the opener", () => {
  const document = {
    activeElement: null,
    body: { style: {} },
    listeners: {},
    addEventListener(name, listener) {
      this.listeners[name] = listener;
    }
  };
  const workspace = interactiveElement(document);
  const shell = interactiveElement(document, {
    dataset: {},
    querySelector: () => workspace
  });
  const open = interactiveElement(document);
  const close = interactiveElement(document);
  const link = interactiveElement(document);
  const sidebar = interactiveElement(document, {
    querySelectorAll: () => [close, link]
  });
  const media = {
    matches: true,
    addEventListener: (_, listener) => {
      media.listener = listener;
    }
  };
  document.querySelector = (selector) => ({
    "[data-app-shell]": shell,
    "[data-nav-open]": open,
    "#primary-navigation": sidebar
  }[selector]);
  document.querySelectorAll = () => [close];

  setupNavigation(document, { matchMedia: () => media });

  assert.equal(sidebar.getAttribute("inert"), "");
  assert.equal(sidebar.getAttribute("aria-hidden"), "true");
  open.listeners.click();
  assert.equal(shell.dataset.navOpened, "true");
  assert.equal(workspace.getAttribute("inert"), "");
  assert.equal(document.activeElement, close);

  const tabEvent = {
    key: "Tab",
    shiftKey: true,
    preventDefault() {
      this.defaultPrevented = true;
    }
  };
  document.listeners.keydown(tabEvent);
  assert.equal(tabEvent.defaultPrevented, true);
  assert.equal(document.activeElement, link);

  document.listeners.keydown({ key: "Escape" });
  assert.equal(shell.dataset.navOpened, "false");
  assert.equal(workspace.getAttribute("inert"), null);
  assert.equal(document.activeElement, open);

  media.matches = false;
  media.listener();
  assert.equal(sidebar.getAttribute("inert"), null);
  assert.equal(sidebar.getAttribute("aria-hidden"), null);
});
