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
      description: "An asyncio Python toolkit for displaying scrolling feeds on RGB LED matrix panels.",
      social: [
        { icon: "github", label: "GitHub", href: "https://github.com/JamesAwesome/led-ticker" },
      ],
      sidebar: [
        { label: "Home", link: "/" },
        { label: "Getting started", link: "/getting-started/" },
        {
          label: "Widgets",
          items: [{ autogenerate: { directory: "widgets" } }],
        },
        {
          label: "Transitions",
          items: [{ autogenerate: { directory: "transitions" } }],
        },
        {
          label: "Pitfalls",
          link: "/pitfalls/",
        },
      ],
    }),
  ],
});
