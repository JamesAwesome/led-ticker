# Collapsible Sidebar Toggle — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm)

> **Revision (implementation eyeball pass):** the original design floated a collapse button over the sidebar's top-left plus a separate fixed edge "»" arrow. In review the floating button overlapped the first nav item. **Final shape:** a **single toggle button placed statically in the header next to the site title**, via a Starlight **`SiteTitle`** component override (not `PageFrame`). The button is always visible on desktop and flips its icon by state (« collapse when open, » expand when collapsed); no separate edge arrow. Everything below about the collapsed-state CSS (`html.sidebar-collapsed` hides `.sidebar` + zeroes `.main-frame` padding, desktop-only), the `head` pre-paint script, `localStorage` persistence, and graceful degradation is unchanged.

## Context

Deferred follow-up from the docs Phase-1 home-page work (memory `project_collapsible_sidebar_followup`). The home page dropped `template: splash` (PR #156) because splash hid the sidebar and made the guide hard to find. This feature restores the roomy, full-width reading feel as an **opt-in toggle** while keeping navigation one click away — the "best of both" resolution.

Docs site is Astro Starlight **0.39.2** at `docs/site/`. Today there is **no** `customCss` array and **no** Starlight component override wired in `astro.config.mjs`; this feature adds the first of each.

## Goal

A site-wide control that collapses/expands the **left navigation sidebar** on desktop. Defaults to open. State persists across pages and reloads. No flash of the wrong state on load. The right-hand "On this page" table of contents is **not** affected. Mobile is untouched (Starlight's existing hamburger drawer stays).

## Approach (chosen)

Approach A from the brainstorm: a Starlight **component override** for the page structure + a **`head` pre-paint script** + a **`customCss`** file.

### Components / files

- **`docs/site/src/styles/sidebar-toggle.css`** (new) — wired via `starlight({ customCss: ['./src/styles/sidebar-toggle.css'] })`.
  - All rules scoped under a desktop-only media query (Starlight's large breakpoint is `min-width: 50rem`; the sidebar only renders as a left pane at/above it). Below the breakpoint the rules are inert, so mobile is untouched.
  - `html.sidebar-collapsed`:
    - hides the left sidebar pane (Starlight renders it as `<nav class="sidebar">` inside the page frame; target the sidebar pane element, verified against the built DOM during implementation),
    - reflows the main content column to full width (collapse the sidebar's grid track / left padding the Starlight layout reserves),
    - hides the in-sidebar collapse button (it's inside the now-hidden pane) and **shows** the fixed edge expand arrow.
  - Default (not collapsed): the edge expand arrow is hidden; the collapse button shows at the sidebar's top-left.
  - A short transition (~150ms) on the reflowed width / sidebar offset for a smooth slide rather than an instant jump.
  - The two controls match Starlight's existing icon-button styling (reuse Starlight CSS variables for color/hover so they track the theme and dark mode).
- **`docs/site/src/components/PageFrame.astro`** (new) — Starlight `PageFrame` override, wired via `starlight({ components: { PageFrame: './src/components/PageFrame.astro' } })`.
  - Renders the default frame: `import Default from '@astrojs/starlight/components/PageFrame.astro'` then `<Default {...Astro.props}><slot /></Default>` (forwarding all named slots Starlight passes — see Implementation note).
  - Adds two sibling controls **outside** the sidebar subtree so they don't disappear when the sidebar is hidden:
    1. **Collapse button** — top-left near the sidebar, a `«` / panel-collapse icon, `aria-label="Collapse sidebar"`.
    2. **Expand arrow** — `position: fixed` at the left screen edge, a `»` icon, `aria-label="Show sidebar"`, visible only when `html.sidebar-collapsed`.
  - A small client `<script>` (module, runs once) wires both controls: click toggles `document.documentElement.classList.toggle('sidebar-collapsed')` and writes the new state to `localStorage` under key `ticker:sidebar-collapsed`.
- **`astro.config.mjs`** (modify) — add to the existing `starlight({ ... })` options:
  - `customCss: ['./src/styles/sidebar-toggle.css']`
  - `components: { PageFrame: './src/components/PageFrame.astro' }`
  - `head: [{ tag: 'script', content: "<pre-paint snippet>" }]` — runs in `<head>` before paint: reads `localStorage['ticker:sidebar-collapsed']`; if `'true'`, adds `sidebar-collapsed` to `document.documentElement.classList`. Wrapped in `try/catch` so a `localStorage`-blocked browser degrades to the default (open) instead of throwing.

### Why these boundaries

- **Pre-paint class in `head`** is the only place that runs before first paint, so it's where FOUC is prevented. It does the read-and-apply; nothing else.
- **PageFrame override** owns the *controls' markup* and the *toggle/persist* behavior. It renders the Starlight default untouched, so we inherit all Starlight layout/accessibility and only add two buttons.
- **`customCss`** owns *appearance and the collapsed-state layout*. No layout logic in JS — JS only flips one class; CSS does the reflow.
- The expand arrow lives in PageFrame (not in the sidebar) specifically because a `position: fixed` element that is a DOM descendant of a `display:none` ancestor is not rendered — so the "show" control must sit outside the collapsible pane.

## Behavior / data flow

1. **Load:** `head` script reads `localStorage`; applies `sidebar-collapsed` to `<html>` if saved true — before paint, no flash. Default (no stored value) = open.
2. **Toggle:** user clicks collapse or expand control → script flips the class on `<html>` and writes the new boolean to `localStorage`. CSS reacts: sidebar slides away / back, content reflows, the visible control swaps.
3. **Navigation:** each page load re-runs the `head` script, so the collapsed/open choice carries across pages.
4. **Mobile (< 50rem):** all collapse CSS is inside the desktop media query and inert; Starlight's hamburger drawer is unchanged. The desktop controls are hidden at mobile widths.

## Error handling / edge cases

- `localStorage` unavailable / throws → `try/catch` in both the `head` script and the toggle handler; feature degrades to "always open, toggle still works in-session but doesn't persist." Never throws into the page.
- Selector drift: Starlight could rename the sidebar pane class across versions. The implementation pins the selector against the **built** DOM (inspect `make docs-build` output / `make docs-dev`) and leaves a comment noting the Starlight version the selector was verified against, so a future Starlight bump has a breadcrumb.
- Keyboard / a11y: both controls are real `<button>`s with `aria-label`s and an `aria-expanded` reflecting state; they're reachable by tab and respond to Enter/Space natively.

## Testing / verification

- **Headless:** `make docs-build` (exit 0, no Astro errors) and `make docs-lint` (0 errors) — confirms the override + customCss + head config compile and links still resolve.
- **Human eyeball (required — can't be verified headlessly), via `make docs-dev`:**
  - Default load shows the sidebar (open); no flash of collapsed-then-open or vice versa on refresh after toggling.
  - Collapse hides the left nav and the content reflows full-width; the edge `»` arrow appears; the right-hand TOC is unaffected.
  - Expand restores the sidebar; state persists across a page navigation and a hard refresh.
  - Dark mode: controls track the theme.
  - Narrow the window below ~50rem: controls disappear and the mobile hamburger behaves as before.

## Out of scope (YAGNI)

- Collapsing/altering the right-hand "On this page" TOC.
- A keyboard shortcut for the toggle.
- Per-section / remembered-scroll sidebar state, animations beyond the simple reflow transition.
- Any change to mobile navigation.
- Server-side / cookie persistence (localStorage is sufficient for a static docs site).

## Delivery

Its own branch `feat/sidebar-collapse-toggle` + PR (a site-wide nav concern, distinct from page content). Docs-only — the Python CI jobs skip; `docs-lint` + `build-and-deploy` run.
