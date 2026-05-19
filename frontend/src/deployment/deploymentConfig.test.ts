import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const repoRoot = resolve(process.cwd(), "..");

function readRepoFile(path: string): string {
	return readFileSync(resolve(repoRoot, path), "utf8");
}

describe("frontend deployment configuration", () => {
	it("uses a multi-stage Node build and Nginx static server instead of Streamlit", () => {
		const dockerfile = readRepoFile("frontend/Dockerfile");

		expect(dockerfile).toContain("FROM node:22-alpine AS build");
		expect(dockerfile).toContain("npm ci");
		expect(dockerfile).toContain("npm run build");
		expect(dockerfile).toContain("FROM nginx:");
		expect(dockerfile).toContain("COPY --from=build");
		expect(dockerfile).toContain("EXPOSE 80");
		expect(dockerfile).not.toContain("streamlit run");
		expect(dockerfile).not.toContain("uv sync");
	});

	it("loads runtime API config before the React module", () => {
		const indexHtml = readRepoFile("frontend/index.html");
		const configScriptIndex = indexHtml.indexOf('src="/config.js"');
		const moduleScriptIndex = indexHtml.indexOf('src="/src/main.tsx"');

		expect(configScriptIndex).toBeGreaterThan(-1);
		expect(moduleScriptIndex).toBeGreaterThan(-1);
		expect(configScriptIndex).toBeLessThan(moduleScriptIndex);
	});

	it("configures SPA fallback and runtime API config generation", () => {
		const nginxConfig = readRepoFile("frontend/nginx.conf");
		const runtimeConfig = readRepoFile("frontend/public/config.js");

		expect(nginxConfig).toContain("try_files $uri $uri/ /index.html");
		expect(nginxConfig).toContain("/config.js");
		expect(runtimeConfig).toContain("window.__PR_REVIEWER_CONFIG__");
		expect(runtimeConfig).toContain("apiBaseUrl");
	});

	it("updates local compose to expose React static frontend and CORS origins", () => {
		const compose = readRepoFile("docker-compose.yml");

		expect(compose).toContain("8080:80");
		expect(compose).toContain("http://localhost:8080,http://localhost:5173");
		expect(compose).toContain(
			"VITE_API_BASE_URL=${VITE_API_BASE_URL:-http://localhost:8000}",
		);
		expect(compose).not.toContain("8501:8501");
		expect(compose).not.toContain("BACKEND_URL=http://backend:8000");
	});

	it("updates Render frontend env semantics from BACKEND_URL to VITE_API_BASE_URL", () => {
		const renderYaml = readRepoFile("render.yaml");

		expect(renderYaml).toContain("healthCheckPath: /");
		expect(renderYaml).toContain("VITE_API_BASE_URL");
		expect(renderYaml).toContain("https://pr-reviewer-api.onrender.com");
		expect(renderYaml).not.toContain("BACKEND_URL");
	});

	it("keeps frontend build artifacts out of Docker build context", () => {
		const dockerignore = readRepoFile(".dockerignore");

		expect(dockerignore).toContain("node_modules");
		expect(dockerignore).toContain("frontend/node_modules");
		expect(dockerignore).toContain("frontend/dist");
	});
});
