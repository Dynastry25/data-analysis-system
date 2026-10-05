/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",

  webpack: (config) => {
    /*
     * Point `plotly.js` at its prebuilt browser bundle.
     *
     * The package's "main" is ./lib/index.js -- unbundled CommonJS source
     * intended for Node. Its image trace does `require("buffer/")` (with the
     * trailing slash, deliberately, so Node resolves the builtin), which no
     * browser bundle can satisfy, so `next build` failed to resolve it.
     *
     * Aliasing to dist/plotly.min.js is the fix the package is built around:
     * that bundle is what its own docs load from a CDN, it has no Node builtin
     * requires, and it is the same code the dev server was already running.
     *
     * This also shrinks the client chunk considerably. Compiling lib/ pulls in
     * every trace and locale individually; the dist bundle is one file.
     */
    config.resolve.alias = {
      ...config.resolve.alias,
      "plotly.js$": "plotly.js/dist/plotly.min.js",
    };
    return config;
  },
};

module.exports = nextConfig;
