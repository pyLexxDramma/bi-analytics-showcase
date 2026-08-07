import type { MetadataRoute } from "next";

/** Демо можно поставить иконкой на домашний экран и открывать без адресной строки. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "BI Analytics",
    short_name: "BI Analytics",
    description: "Строительная аналитика девелоперских проектов",
    start_url: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#f8f9fb",
    theme_color: "#059669",
    lang: "ru",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/apple-touch-icon.png",
        sizes: "180x180",
        type: "image/png",
        purpose: "any",
      },
    ],
  };
}
