import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import starlightLlmsTxt from "starlight-llms-txt";
import remarkGfm from "remark-gfm";
import { fileURLToPath } from "node:url";
import path from "node:path";
import structuredData from "./src/structured-data.json";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // Custom domain. Cloudflare Pages also serves preview deploys at
  // `<branch>.led-ticker.pages.dev` for in-flight PRs — the custom
  // domain only fronts the production build.
  site: "https://docs.ledticker.dev",
  // Astro 6.4 reworked the Markdown pipeline (https://astro.build/blog/astro-640/)
  // and its new default wiring stopped applying GFM to our `.mdx` pages, silently
  // breaking every markdown-authored pipe-table (they degrade to literal text).
  //
  // We restore GFM by re-adding the `remark-gfm` plugin. It MUST go on the
  // legacy `markdown.remarkPlugins` array, NOT the new `markdown.processor` API:
  // these pages are `.mdx`, processed by `@astrojs/mdx@5.x` (pinned by Starlight
  // 0.39.2 — the latest release), which predates the 6.4 rework and only reads
  // the legacy markdown options. A `markdown.processor` is silently ignored for
  // MDX here (verified: 0 tables). `@astrojs/mdx@6` adopts the new pipeline but
  // Starlight does not depend on it yet.
  //
  // DEFERRED: once Starlight ships Astro-6.4-pipeline support, migrate this to
  // `markdown.processor: unified({ remarkPlugins: [remarkGfm] })` (or drop it
  // entirely if GFM defaults are restored) and delete the `remark-gfm` dep.
  // Tracking + full rationale:
  // docs/superpowers/specs/2026-05-30-docs-mdx-gfm-tables-design.md.
  markdown: {
    remarkPlugins: [remarkGfm],
  },
  vite: {
    server: {
      fs: {
        allow: [path.resolve(__dirname, "../../content-source")],
      },
    },
  },
  integrations: [
    starlight({
      plugins: [
        starlightLlmsTxt({
          projectName: "led-ticker",
          description:
            "An asyncio Python toolkit for displaying scrolling feeds on RGB LED matrix panels.",
        }),
      ],
      title: "led-ticker",
      description:
        "An asyncio Python toolkit for displaying scrolling feeds on RGB LED matrix panels.",
      customCss: ["./src/styles/sidebar-toggle.css"],
      components: {
        SiteTitle: "./src/components/SiteTitle.astro",
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
        {
          tag: "link",
          attrs: {
            rel: "alternate",
            type: "text/markdown",
            href: "/llms.txt",
            title: "led-ticker docs as Markdown (for LLMs/agents)",
          },
        },
        {
          tag: "script",
          attrs: { type: "application/ld+json" },
          content: JSON.stringify(structuredData),
        },
      ],
      social: [
        { icon: "github", label: "GitHub", href: "https://github.com/JamesAwesome/led-ticker" },
      ],
      sidebar: [
        { label: "Home", link: "/" },
        { label: "Getting started", link: "/getting-started/" },
        { label: "Why led-ticker?", link: "/why-led-ticker/" },
        {
          label: "Tutorial",
          items: [
            { label: "1. Setup", link: "/tutorial/01-setup/" },
            { label: "2. Your first config", link: "/tutorial/02-first-config/" },
            { label: "3. Multi-widget sign", link: "/tutorial/03-multi-widget/" },
            { label: "4. Custom branding", link: "/tutorial/04-custom-branding/" },
            { label: "5. Polish & deploy", link: "/tutorial/05-polish/" },
          ],
        },
        {
          label: "Widgets",
          items: [
            // Overview index first (matches the sibling Transitions
            // group, where /transitions/ is the natural top entry),
            // then `message` pinned ahead of the rest since it's
            // the most-used widget — letting the autogenerate sort
            // would bury it alphabetically at position 7.
            { label: "All widgets", link: "/widgets/" },
            {
              label: "Core widgets",
              items: [
                { label: "message", link: "/widgets/message/" },
                { label: "countdown", link: "/widgets/countdown/" },
                { label: "countup", link: "/widgets/countup/" },
                { label: "clock", link: "/widgets/clock/" },
                { label: "two_row", link: "/widgets/two_row/" },
                { label: "gif", link: "/widgets/gif/" },
                { label: "image", link: "/widgets/image/" },
              ],
            },
            {
              label: "Plugin widgets",
              items: [
                { label: "baseball.scores", link: "/widgets/mlb/" },
                { label: "baseball.standings", link: "/widgets/mlb_standings/" },
                { label: "crypto.coingecko", link: "/widgets/crypto-coingecko/" },
                { label: "pool", link: "/widgets/pool/" },
                { label: "calendar.events", link: "/widgets/calendar/" },
                { label: "rss.feed", link: "/widgets/rss_feed/" },
                { label: "weather.current", link: "/widgets/weather/" },
              ],
            },
          ],
        },
        {
          label: "Plugins",
          items: [
            {
              label: "Using plugins",
              items: [
                { label: "Plugins overview", link: "/plugins/" },
                { label: "Available plugins", link: "/plugins/available/" },
              ],
            },
            {
              label: "Building plugins",
              items: [
                { label: "API reference", link: "/plugins/api-reference/" },
                {
                  label: "Authoring a plugin",
                  items: [
                    { label: "1. Scaffold & register", link: "/plugins/authoring/01-scaffold/" },
                    { label: "2. Build the widget", link: "/plugins/authoring/02-widget/" },
                    { label: "3. Package & install", link: "/plugins/authoring/03-package/" },
                    { label: "4. Beyond widgets", link: "/plugins/authoring/04-beyond-widgets/" },
                  ],
                },
                {
                  label: "Extending led-ticker",
                  items: [
                    { label: "Custom emoji", link: "/plugins/extending/custom-emoji/" },
                    {
                      label: "Writing a transition",
                      link: "/plugins/extending/writing-a-transition/",
                    },
                    {
                      label: "Custom color provider",
                      link: "/plugins/extending/custom-color-provider/",
                    },
                    { label: "Service plugins", link: "/plugins/extending/service-plugins/" },
                  ],
                },
              ],
            },
          ],
        },
        {
          label: "Transitions",
          items: [{ autogenerate: { directory: "transitions" } }],
        },
        {
          label: "Concepts",
          items: [
            { label: "How rendering works", link: "/concepts/how-rendering-works/" },
            { label: "Animations", link: "/concepts/animations/" },
            { label: "Borders", link: "/concepts/borders/" },
            { label: "Busy light", link: "/concepts/busy-light/" },
            { label: "Color providers", link: "/concepts/color-providers/" },
            { label: "Display", link: "/concepts/display/" },
            { label: "Fonts", link: "/concepts/fonts/" },
            { label: "Config hot-reload", link: "/concepts/hot-reload/" },
            { label: "Sections and modes", link: "/concepts/sections-and-modes/" },
            { label: "Value tokens", link: "/concepts/value-tokens/" },
            { label: "Web status UI", link: "/concepts/web-status-ui/" },
          ],
        },
        {
          // Inline emoji is a content-author concern (which slugs render?
          // what's the fallback for unknown ones?) — sits naturally next
          // to Concepts, before deeper hardware/reference material.
          label: "Assets",
          items: [{ autogenerate: { directory: "assets" } }],
        },
        {
          label: "Tools",
          items: [{ autogenerate: { directory: "tools" } }],
        },
        // Validation rules sit next to Tools — they're what
        // `led-ticker validate` reports.
        { label: "Validation rules", link: "/pitfalls/" },
        {
          label: "Reference",
          items: [{ autogenerate: { directory: "reference" } }],
        },
        {
          label: "Hardware",
          items: [
            // Build pages and embedded reference configs alternate by sign
            // type so a reader scanning the sidebar can pair each build
            // walkthrough with the working config it produces. Reference
            // configs link to the #reference-config anchor on the build
            // page so a click lands directly on the embedded TOML.
            { label: "Hardware: Bigsign reference build", link: "/hardware/bigsign/" },
            {
              label: 'Bigsign config - "Showroom"',
              link: "/hardware/bigsign/#reference-config",
            },
            {
              label: "Hardware: Smallsign reference build",
              link: "/hardware/smallsign/",
            },
            {
              label: 'Smallsign config - "Office Ticker"',
              link: "/hardware/smallsign/#reference-config",
            },
            {
              label: "Hardware: Longboi reference build",
              link: "/hardware/longboi/",
            },
            {
              label: 'Longboi config - "Meeting Backdrop"',
              link: "/hardware/longboi/#config-snippet",
            },
            {
              label: "Hardware: Building your own",
              link: "/hardware/building-your-own/",
            },
          ],
        },
        // Inspiration / browsing — last, because reaching it from
        // anywhere else is a sign you've already learned what you came for.
        { label: "Sign Showcase", link: "/showcase/" },
      ],
    }),
  ],
});
