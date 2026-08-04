import type { MetadataRoute } from "next";

/** Демо можно поставить иконкой на домашний экран и открывать без адресной строки. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "BI Analytics Showcase",
    short_name: "BI Analytics",
    description: "Демо аналитических дашбордов девелоперских проектов",
    start_url: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#f8f9fb",
    theme_color: "#f8f9fb",
    lang: "ru",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
    ],
  };
}
