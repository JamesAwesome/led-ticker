import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  site: "https://jamesawesome.github.io",
  base: "/led-ticker",
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
