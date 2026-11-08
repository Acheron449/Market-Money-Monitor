module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended"],
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: "latest", sourceType: "module" },
  plugins: ["react-hooks", "react-refresh"],
  ignorePatterns: ["dist", "node_modules", "*.config.js", ".eslintrc.cjs"],
  rules: {
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",
    "react-refresh/only-export-components": "off",
    "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
  },
  overrides: [
    {
      files: [
        "src/**/*.test.ts",
        "src/**/*.test.tsx",
        "src/test/**",
        "e2e/**",
        "playwright.config.ts",
        "vite.config.ts",
      ],
      env: { node: true },
      rules: { "react-refresh/only-export-components": "off" },
    },
  ],
};
