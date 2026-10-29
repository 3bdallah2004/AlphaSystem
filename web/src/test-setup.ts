import "@testing-library/jest-dom/vitest";
import themeSource from "../public/theme.js?raw";

// jsdom does not execute index.html's parser-blocking startup script.
new Function("window", "document", themeSource)(window, document);
