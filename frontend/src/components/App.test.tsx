import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
	return new Response(JSON.stringify(body), {
		status: 200,
		headers: { "Content-Type": "application/json" },
		...init,
	});
}

describe("App smoke UI", () => {
	afterEach(() => {
		vi.unstubAllEnvs();
		vi.restoreAllMocks();
	});

	it("renders the app shell, loaded providers, and review form", async () => {
		vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
		vi.stubGlobal(
			"fetch",
			vi
				.fn()
				.mockResolvedValueOnce(jsonResponse({ status: "ok", neo4j: false }))
				.mockResolvedValueOnce(
					jsonResponse({
						providers: [
							{
								key: "cerebras",
								description: "FREE - fast",
								default_model: "llama3",
								key_label: "HuggingFace API Key",
								supports_structured_output: true,
							},
						],
					}),
				),
		);

		render(<App />);

		expect(
			screen.getByRole("heading", { name: /pr code reviewer/i }),
		).toBeInTheDocument();
		expect(screen.getByText(/react frontend scaffold/i)).toBeInTheDocument();
		await waitFor(() =>
			expect(screen.getByText(/backend: ok/i)).toBeInTheDocument(),
		);
		expect(
			screen.getByRole("option", { name: /cerebras — free - fast/i }),
		).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /run review/i })).toBeDisabled();
	});

	it("renders sanitized API errors when provider loading fails", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockRejectedValue(new Error("token ghp_secret should not leak")),
		);

		render(<App />);

		await waitFor(() =>
			expect(screen.getByText(/backend unavailable/i)).toBeInTheDocument(),
		);
		expect(screen.getAllByText(/network error/i).length).toBeGreaterThan(0);
		expect(screen.queryByText(/ghp_secret/i)).not.toBeInTheDocument();
	});
});
