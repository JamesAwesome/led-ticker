import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // Update `site` to a custom domain after Cloudflare Pages setup.
  // Default `*.pages.dev` URL works without `site` set, but sitemap
  // will use relative URLs until this is filled in.
  site: "https://led-ticker.pages.dev",
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
          label: "Tools",
          items: [{ autogenerate: { directory: "tools" } }],
        },
        {
          label: "Hardware",
          items: [{ autogenerate: { directory: "hardware" } }],
        },
        {
          label: "Reference",
          items: [{ autogenerate: { directory: "reference" } }],
        },
        {
          label: "Assets",
          items: [{ autogenerate: { directory: "assets" } }],
        },
        { label: "Showcase", link: "/showcase/" },
        { label: "Pitfalls", link: "/pitfalls/" },
      ],
    }),
  ],
});
