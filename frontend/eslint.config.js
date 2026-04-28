import importX from "eslint-plugin-import-x";

export default [
    {
        files: ["**/*.js"],
        ignores: ["node_modules/**"],
        plugins: {
            import: importX,
        },
        languageOptions: {
            ecmaVersion: "latest",
            sourceType: "module",
            globals: {
                URLSearchParams: "readonly",
                CustomEvent: "readonly",
                Event: "readonly",
                File: "readonly",
                FormData: "readonly",
                HTMLElement: "readonly",
                HTMLInputElement: "readonly",
                HTMLSelectElement: "readonly",
                HTMLButtonElement: "readonly",
                KeyboardEvent: "readonly",
                Node: "readonly",
                document: "readonly",
                fetch: "readonly",
                history: "readonly",
                performance: "readonly",
                requestAnimationFrame: "readonly",
                sessionStorage: "readonly",
                window: "readonly",
                console: "readonly",
            },
        },
        rules: {
            "no-var": "error",
            "prefer-const": "error",
            "object-shorthand": ["error", "always"],
            "no-console": ["warn", {
                allow: ["warn", "error"],
            }],
            "no-param-reassign": "error",
            "import/no-cycle": "error",
            "no-unused-vars": ["error", {
                args: "none",
                caughtErrors: "none",
            }],
        },
    },
];
