import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // Custom domain. Cloudflare Pages also serves preview deploys at
  // `<branch>.led-ticker.pages.dev` for in-flight PRs — the custom
  // domain only fronts the production build.
  site: "https://docs.ledticker.dev",
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
          ],
        },
        {
          label: "Transitions",
          items: [{ autogenerate: { directory: "transitions" } }],
        },
        {
          label: "Concepts",
          items: [{ autogenerate: { directory: "concepts" } }],
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
              label: "Hardware: Building your own",
              link: "/hardware/building-your-own/",
            },
          ],
        },
        {
          label: "Reference",
          items: [{ autogenerate: { directory: "reference" } }],
        },
        { label: "Showcase", link: "/showcase/" },
        { label: "Validation rules", link: "/pitfalls/" },
      ],
    }),
  ],
});
