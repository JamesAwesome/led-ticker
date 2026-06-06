import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import remarkGfm from "remark-gfm";
import { fileURLToPath } from "node:url";
import path from "node:path";

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
      title: "led-ticker",
      description:
        "An asyncio Python toolkit for displaying scrolling feeds on RGB LED matrix panels.",
      social: [
        { icon: "github", label: "GitHub", href: "https://github.com/JamesAwesome/led-ticker" },
      ],
      sidebar: [
        { label: "Home", link: "/" },
        { label: "Getting started", link: "/getting-started/" },
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
            { label: "message", link: "/widgets/message/" },
            { label: "countdown", link: "/widgets/countdown/" },
            { label: "two_row", link: "/widgets/two_row/" },
            { label: "weather", link: "/widgets/weather/" },
            { label: "rss_feed", link: "/widgets/rss_feed/" },
            { label: "gif", link: "/widgets/gif/" },
            { label: "image", link: "/widgets/image/" },
            { label: "mlb", link: "/widgets/mlb/" },
            { label: "mlb_standings", link: "/widgets/mlb_standings/" },
            { label: "coinbase", link: "/widgets/coinbase/" },
            { label: "coingecko", link: "/widgets/coingecko/" },
            { label: "etherscan", link: "/widgets/etherscan/" },
            { label: "pool (plugin)", link: "/widgets/pool/" },
          ],
        },
        {
          label: "Plugins",
          items: [
            { label: "Plugins overview", link: "/plugins/" },
            { label: "Available plugins", link: "/plugins/available/" },
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
                { label: "Writing a transition", link: "/plugins/extending/writing-a-transition/" },
                {
                  label: "Custom color provider",
                  link: "/plugins/extending/custom-color-provider/",
                },
                { label: "Service plugins", link: "/plugins/extending/service-plugins/" },
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
            { label: "Sections and modes", link: "/concepts/sections-and-modes/" },
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
