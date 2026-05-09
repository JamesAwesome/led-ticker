import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  site: "https://jamesawesome.github.io",
  base: "/led-ticker",
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
      social: {
        github: "https://github.com/JamesAwesome/led-ticker",
      },
      sidebar: [
        { label: "Home", link: "/" },
        { label: "Getting started", link: "/getting-started/" },
        {
          label: "Widgets",
          autogenerate: { directory: "widgets" },
        },
        {
          label: "Transitions",
          autogenerate: { directory: "transitions" },
        },
        {
          label: "Footguns",
          link: "/footguns/",
        },
      ],
    }),
  ],
});
