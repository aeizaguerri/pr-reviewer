import { describe, expect, it } from "vitest";
import { parseRepoSlug, validateReviewForm } from "./validation";

const baseInput = {
	repoSlug: "gentleman-programming/pr-reviewer",
	prNumber: "42",
	provider: "cerebras",
	providerApiKey: "provider-key",
	githubToken: "github-token",
	model: "",
	baseUrlOverride: "",
};

describe("parseRepoSlug", () => {
	it("parses owner/repo slugs and trims surrounding whitespace", () => {
		expect(parseRepoSlug(" gentleman-programming/pr-reviewer ")).toEqual({
			owner: "gentleman-programming",
			repo: "pr-reviewer",
		});
	});

	it("rejects empty owner, empty repo, and malformed slugs", () => {
		expect(parseRepoSlug("/repo")).toBeNull();
		expect(parseRepoSlug("owner/")).toBeNull();
		expect(parseRepoSlug("owner/repo/extra")).toBeNull();
	});
});

describe("validateReviewForm", () => {
	it("creates a review request for valid remote-provider input", () => {
		expect(validateReviewForm(baseInput)).toEqual({
			valid: true,
			value: {
				request: {
					owner: "gentleman-programming",
					repo: "pr-reviewer",
					pr_number: 42,
					provider: "cerebras",
					model: "",
					base_url_override: "",
				},
				providerApiKey: "provider-key",
				githubToken: "github-token",
			},
		});
	});

	it("allows optional model and base URL overrides", () => {
		expect(
			validateReviewForm({
				...baseInput,
				model: "llama-3.3-70b",
				baseUrlOverride: " http://ollama:11434/v1 ",
			}),
		).toMatchObject({
			valid: true,
			value: {
				request: {
					model: "llama-3.3-70b",
					base_url_override: "http://ollama:11434/v1",
				},
			},
		});
	});

	it("requires repo slug, a positive integer PR number, provider, and GitHub token", () => {
		expect(
			validateReviewForm({
				...baseInput,
				repoSlug: "owner/",
				prNumber: "0",
				provider: "",
				githubToken: "",
			}),
		).toEqual({
			valid: false,
			errors: {
				repoSlug: "Use the format owner/repo.",
				prNumber: "PR number must be a positive integer.",
				provider: "Choose a provider.",
				githubToken: "GitHub token is required.",
			},
		});
	});

	it("requires provider API keys for remote providers", () => {
		expect(
			validateReviewForm({ ...baseInput, providerApiKey: "  " }),
		).toMatchObject({
			valid: false,
			errors: { providerApiKey: "Provider API key is required." },
		});
	});

	it("uses the backend-compatible Ollama fallback token when local provider key is empty", () => {
		expect(
			validateReviewForm({
				...baseInput,
				provider: "ollama",
				providerApiKey: "",
			}),
		).toMatchObject({
			valid: true,
			value: {
				providerApiKey: "ollama",
				request: { provider: "ollama" },
			},
		});
	});
});
