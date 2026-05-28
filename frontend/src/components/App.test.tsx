import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

	it("renders the workspace shell and review form after health check", async () => {
		vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
		vi.stubGlobal(
			"fetch",
			vi
				.fn()
				.mockResolvedValueOnce(jsonResponse({ status: "ok", neo4j: false })),
		);

		render(<App />);

		expect(screen.queryByText(/react frontend scaffold/i)).not.toBeInTheDocument();
		expect(
			screen.getByRole("button", { name: /collapse sidebar/i }),
		).toBeInTheDocument();
		await waitFor(() =>
			expect(screen.getByText(/backend: ok/i)).toBeInTheDocument(),
		);
		// ReviewForm renders without requiring providers to load
		expect(screen.getByLabelText(/repository/i)).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /run review/i })).toBeDisabled();
		// Provider controls must not be present
		expect(screen.queryByLabelText(/^provider$/i)).not.toBeInTheDocument();
	});

	it("renders review results after successful form submission", async () => {
		vi.stubGlobal(
			"fetch",
			vi
				.fn()
				.mockResolvedValueOnce(jsonResponse({ status: "ok", neo4j: false }))
				.mockResolvedValueOnce(
					jsonResponse({
						summary: "No bugs detected.",
						approved: true,
						bugs: [],
						impact_warnings: [],
						review_health: { status: "complete", warnings: [] },
					}),
				),
		);
		render(<App />);

		const user = userEvent.setup();
		await user.type(
			await screen.findByLabelText(/repository/i),
			"gentleman-programming/pr-reviewer",
		);
		await user.type(screen.getByLabelText(/pull request number/i), "42");
		await user.type(screen.getByLabelText(/hugging face api key/i), "hf-secret");
		await user.type(screen.getByLabelText(/github token/i), "github-secret");
		await user.click(screen.getByRole("button", { name: /run review/i }));

		await waitFor(() =>
			expect(screen.getByText("✅ Approved")).toBeInTheDocument(),
		);
		expect(screen.getByText("Ready to merge")).toBeInTheDocument();
		expect(screen.getByText("No bugs detected.")).toBeInTheDocument();
		expect(
			screen.queryByText(/detailed result rendering is coming next/i),
		).not.toBeInTheDocument();
	});

	it("renders sanitized API errors when health check fails", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockRejectedValue(new Error("token ghp_secret should not leak")),
		);

		render(<App />);

		await waitFor(() =>
			expect(screen.getByText(/backend unavailable/i)).toBeInTheDocument(),
		);
		expect(screen.queryByText(/ghp_secret/i)).not.toBeInTheDocument();
	});
});
