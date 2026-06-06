# Collapsible Sidebar Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a desktop-only, default-open toggle that collapses/expands the Starlight docs left navigation sidebar, persisted in `localStorage` with no flash on load.

**Architecture:** A Starlight `PageFrame` component override renders the default frame plus two controls (a collapse button and a fixed edge expand-arrow) as siblings *outside* the sidebar subtree. A `customCss` file keys off `html.sidebar-collapsed` to hide the sidebar and reflow the main column full-width inside a `min-width: 50rem` media query. A `head` pre-paint script applies the saved class before first paint.

**Tech Stack:** Astro Starlight 0.39.2, plain CSS, a small vanilla-JS `<script>`. No new dependencies.

**Worktree:** `.claude/worktrees/sidebar-toggle`, branch `feat/sidebar-collapse-toggle` (already created off origin/main).
**Commit:** prefix git with `-c core.hooksPath=/dev/null` (pre-commit framework absent in worktree).
**No automated unit test exists for Astro/CSS here** — verification gates are `make docs-build` + `make docs-lint` (both run `pnpm install` themselves) plus a required human-eyeball pass (Task 4). All paths in `astro.config.mjs` are relative to `docs/site/`.

---

### Task 1: customCss — collapsed-state layout + control styling

**Files:**
- Create: `docs/site/src/styles/sidebar-toggle.css`
- Modify: `docs/site/astro.config.mjs` (add `customCss` to the `starlight({...})` options)

- [ ] **Step 1: Create the stylesheet**

Create `docs/site/src/styles/sidebar-toggle.css` with exactly:

```css
/*
 * Collapsible left-sidebar toggle.
 * Selectors verified against Starlight 0.39.2 PageFrame.astro:
 *   <nav class="sidebar"> > <div id="starlight__sidebar" class="sidebar-pane">
 *   <div class="main-frame"> offset by padding-inline-start: var(--sl-content-inline-start)
 * Desktop breakpoint matches Starlight's own: min-width: 50rem.
 */

/* Controls hidden by default — covers mobile (< 50rem), where Starlight's
   hamburger drawer stays in charge. */
#sidebar-collapse-btn,
#sidebar-expand-btn {
  display: none;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  border: 1px solid var(--sl-color-gray-5);
  border-radius: 0.5rem;
  background-color: var(--sl-color-bg-nav);
  color: var(--sl-color-text-accent);
  cursor: pointer;
}

#sidebar-collapse-btn:hover,
#sidebar-expand-btn:hover {
  background-color: var(--sl-color-gray-6);
}

@media (min-width: 50rem) {
  /* Smooth reflow rather than an instant jump. */
  .main-frame {
    transition: padding-inline-start 150ms ease;
  }

  /* Collapse control: top-left, by the sidebar; shown when expanded. */
  #sidebar-collapse-btn {
    display: flex;
    position: fixed;
    top: calc(var(--sl-nav-height) + 0.5rem);
    inset-inline-start: 0.5rem;
    z-index: calc(var(--sl-z-index-menu) + 1);
  }

  /* Expand control: left screen edge, vertically centered; shown only when collapsed. */
  #sidebar-expand-btn {
    position: fixed;
    top: 50%;
    inset-inline-start: 0;
    transform: translateY(-50%);
    border-inline-start: 0;
    border-start-start-radius: 0;
    border-end-start-radius: 0;
    z-index: var(--sl-z-index-navbar);
  }

  html.sidebar-collapsed .sidebar {
    display: none;
  }
  html.sidebar-collapsed .main-frame {
    padding-inline-start: 0;
  }
  html.sidebar-collapsed #sidebar-collapse-btn {
    display: none;
  }
  html.sidebar-collapsed #sidebar-expand-btn {
    display: flex;
  }
}
```

- [ ] **Step 2: Wire `customCss` into the Starlight config**

In `docs/site/astro.config.mjs`, inside the `starlight({ ... })` options object, add a `customCss` entry. Place it immediately after the `description:` property:

```js
      description:
        "An asyncio Python toolkit for displaying scrolling feeds on RGB LED matrix panels.",
      customCss: ["./src/styles/sidebar-toggle.css"],
```

- [ ] **Step 3: Verify build + lint**

Run from the worktree:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/sidebar-toggle
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
```
Expected: `BUILD=0` and `LINT=0` (the CSS references `#sidebar-collapse-btn` / `.sidebar-collapsed` that don't exist yet — harmless; CSS for absent elements is inert).

- [ ] **Step 4: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/sidebar-toggle
git add docs/site/src/styles/sidebar-toggle.css docs/site/astro.config.mjs
git -c core.hooksPath=/dev/null commit -m "docs: add collapsible-sidebar CSS + wire customCss"
```

---

### Task 2: PageFrame override — controls + toggle behavior

**Files:**
- Create: `docs/site/src/components/PageFrame.astro`
- Modify: `docs/site/astro.config.mjs` (add `components` to the `starlight({...})` options)

- [ ] **Step 1: Create the override component**

Create `docs/site/src/components/PageFrame.astro` with exactly:

```astro
---
// Override of Starlight's PageFrame. Renders the stock frame unchanged
// (forwarding all named slots) and adds the sidebar collapse/expand
// controls as siblings OUTSIDE the sidebar subtree — a position:fixed
// element nested in a display:none ancestor would not render, so the
// "show" control must live here, not inside the collapsible pane.
import Default from "@astrojs/starlight/components/PageFrame.astro";
---

<Default {...Astro.props}>
  <slot name="header" slot="header" />
  <slot name="sidebar" slot="sidebar" />
  <slot />
</Default>

<button
  id="sidebar-collapse-btn"
  type="button"
  aria-label="Collapse sidebar"
  aria-controls="starlight__sidebar"
  aria-expanded="true"
>
  <svg
    aria-hidden="true"
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
  >
    <path d="M15 18l-6-6 6-6"></path>
  </svg>
</button>

<button
  id="sidebar-expand-btn"
  type="button"
  aria-label="Show sidebar"
  aria-controls="starlight__sidebar"
  aria-expanded="false"
>
  <svg
    aria-hidden="true"
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
  >
    <path d="M9 18l6-6-6-6"></path>
  </svg>
</button>

<script>
  const KEY = "ticker:sidebar-collapsed";

  function syncAria(collapsed) {
    const expanded = String(!collapsed);
    document
      .getElementById("sidebar-collapse-btn")
      ?.setAttribute("aria-expanded", expanded);
    document
      .getElementById("sidebar-expand-btn")
      ?.setAttribute("aria-expanded", expanded);
  }

  function setCollapsed(collapsed) {
    document.documentElement.classList.toggle("sidebar-collapsed", collapsed);
    syncAria(collapsed);
    try {
      localStorage.setItem(KEY, String(collapsed));
    } catch (e) {
      /* localStorage blocked — toggle still works for this session. */
    }
  }

  // Keep aria honest with the pre-paint class applied in <head>.
  syncAria(document.documentElement.classList.contains("sidebar-collapsed"));

  document
    .getElementById("sidebar-collapse-btn")
    ?.addEventListener("click", () => setCollapsed(true));
  document
    .getElementById("sidebar-expand-btn")
    ?.addEventListener("click", () => setCollapsed(false));
</script>
```

- [ ] **Step 2: Wire the `components` override into the Starlight config**

In `docs/site/astro.config.mjs`, inside the `starlight({ ... })` options object, add a `components` entry immediately after the `customCss` line from Task 1:

```js
      customCss: ["./src/styles/sidebar-toggle.css"],
      components: {
        PageFrame: "./src/components/PageFrame.astro",
      },
```

- [ ] **Step 3: Verify build + lint**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/sidebar-toggle
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
grep -q 'id="sidebar-collapse-btn"' docs/site/dist/index.html && echo "BTN_IN_HTML=yes" || echo "BTN_IN_HTML=no"
```
Expected: `BUILD=0`, `LINT=0`, `BTN_IN_HTML=yes` (the override renders the button into every built page).

- [ ] **Step 4: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/sidebar-toggle
git add docs/site/src/components/PageFrame.astro docs/site/astro.config.mjs
git -c core.hooksPath=/dev/null commit -m "docs: add sidebar collapse/expand controls via PageFrame override"
```

---

### Task 3: Pre-paint script — persistence without FOUC

**Files:**
- Modify: `docs/site/astro.config.mjs` (add `head` to the `starlight({...})` options)

- [ ] **Step 1: Add the `head` pre-paint script**

In `docs/site/astro.config.mjs`, inside the `starlight({ ... })` options object, add a `head` entry immediately after the `components` block from Task 2:

```js
      components: {
        PageFrame: "./src/components/PageFrame.astro",
      },
      // Applies the saved collapsed state to <html> BEFORE first paint so the
      // layout never flashes the wrong state on load. try/catch so a
      // localStorage-blocked browser degrades to the default (open).
      head: [
        {
          tag: "script",
          content:
            "try{if(localStorage.getItem('ticker:sidebar-collapsed')==='true'){document.documentElement.classList.add('sidebar-collapsed')}}catch(e){}",
        },
      ],
```

- [ ] **Step 2: Verify build + lint + that the snippet is inlined in `<head>`**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/sidebar-toggle
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
grep -q "ticker:sidebar-collapsed" docs/site/dist/index.html && echo "HEAD_SCRIPT=yes" || echo "HEAD_SCRIPT=no"
```
Expected: `BUILD=0`, `LINT=0`, `HEAD_SCRIPT=yes`.

- [ ] **Step 3: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/sidebar-toggle
git add docs/site/astro.config.mjs
git -c core.hooksPath=/dev/null commit -m "docs: apply saved sidebar state pre-paint to avoid flash"
```

---

### Task 4: Full verification + human-eyeball pass

**Files:** none (verification only).

- [ ] **Step 1: Headless gate**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/sidebar-toggle
make docs-build; echo "BUILD=$?"
make docs-lint; echo "LINT=$?"
```
Expected: `BUILD=0`, `LINT=0`.

- [ ] **Step 2: Human-eyeball pass (cannot be verified headlessly — flagged in the spec).**

Start the dev server and visually confirm each item. Tuning the exact control placement / reflow feel is expected here:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/sidebar-toggle
make docs-dev    # open the printed localhost URL in a browser
```
Confirm on a desktop-width window:
- Default load shows the sidebar (open); the collapse control sits top-left by the sidebar.
- Clicking collapse hides the left nav and the content reflows to full width with a smooth ~150ms slide; the edge `»` arrow appears at the left.
- The right-hand "On this page" TOC is unaffected by collapse/expand.
- Clicking the edge arrow restores the sidebar.
- State persists across a page navigation and a hard refresh, with **no flash** of the wrong state.
- Toggle dark mode: both controls track the theme.
- Narrow the window below ~50rem: both controls disappear and Starlight's hamburger drawer behaves exactly as before.

If placement/feel needs adjustment, edit `docs/site/src/styles/sidebar-toggle.css` (and/or the SVG paths in `PageFrame.astro`), re-check in the browser, then:
```bash
git add docs/site/src/styles/sidebar-toggle.css docs/site/src/components/PageFrame.astro
git -c core.hooksPath=/dev/null commit -m "docs: tune sidebar toggle placement/feel from eyeball pass"
```

- [ ] **Step 3: Final code review + open the PR** (per finishing-a-development-branch).

---

## Self-Review

**1. Spec coverage:**
- Left-nav-only collapse, default open → Task 1 CSS (`html.sidebar-collapsed .sidebar`/`.main-frame`); TOC untouched (no rule targets the right sidebar). ✓
- Top-left collapse button + fixed edge expand arrow outside the sidebar subtree → Task 2 PageFrame override. ✓
- `localStorage` persistence + no FOUC → Task 3 `head` pre-paint script + Task 2 toggle script writing `ticker:sidebar-collapsed`. ✓
- Desktop-only; mobile untouched → all collapse rules inside `@media (min-width: 50rem)`; controls `display:none` by default. ✓
- Graceful `localStorage` failure → `try/catch` in both scripts. ✓
- Smooth reflow (~150ms) → `.main-frame { transition }`. ✓
- a11y (real buttons, aria-label, aria-expanded, aria-controls) → Task 2. ✓
- customCss + components + head are the first of each in the config → Tasks 1–3 add them. ✓
- Verification = build + lint headless + human eyeball → Task 4. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete CSS / Astro / JS / config. ✓

**3. Type/identifier consistency:** `localStorage` key `ticker:sidebar-collapsed`, class `sidebar-collapsed`, ids `sidebar-collapse-btn` / `sidebar-expand-btn`, and `aria-controls="starlight__sidebar"` (matches Starlight's `id="starlight__sidebar"`) are identical across the CSS, the component, the toggle script, and the head script. ✓
