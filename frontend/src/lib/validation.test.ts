import { describe, expect, it } from "vitest";
import { parseRepoSlug, validateReviewForm } from "./validation";

const baseInput = {
	repoSlug: "gentleman-programming/pr-reviewer",
	prNumber: "42",
	providerApiKey: "hf-test-key",
	githubToken: "github-token",
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
	it("creates a review request with only owner, repo, and pr_number for valid input", () => {
		expect(validateReviewForm(baseInput)).toEqual({
			valid: true,
			value: {
				request: {
					owner: "gentleman-programming",
					repo: "pr-reviewer",
					pr_number: 42,
				},
				providerApiKey: "hf-test-key",
				githubToken: "github-token",
			},
		});
	});

	it("requires repo slug in owner/repo format", () => {
		expect(
			validateReviewForm({
				...baseInput,
				repoSlug: "owner/",
			}),
		).toMatchObject({
			valid: false,
			errors: { repoSlug: "Use the format owner/repo." },
		});
	});

	it("requires a positive integer PR number", () => {
		expect(
			validateReviewForm({
				...baseInput,
				prNumber: "0",
			}),
		).toMatchObject({
			valid: false,
			errors: { prNumber: "PR number must be a positive integer." },
		});
	});

	it("requires a non-empty Hugging Face API key", () => {
		expect(
			validateReviewForm({
				...baseInput,
				providerApiKey: "",
			}),
		).toMatchObject({
			valid: false,
			errors: { providerApiKey: "Hugging Face API key is required." },
		});
	});

	it("requires a non-empty GitHub token", () => {
		expect(
			validateReviewForm({
				...baseInput,
				githubToken: "",
			}),
		).toMatchObject({
			valid: false,
			errors: { githubToken: "GitHub token is required." },
		});
	});

	it("reports multiple missing fields at once", () => {
		expect(
			validateReviewForm({
				repoSlug: "",
				prNumber: "",
				providerApiKey: "",
				githubToken: "",
			}),
		).toEqual({
			valid: false,
			errors: {
				repoSlug: "Use the format owner/repo.",
				prNumber: "PR number must be a positive integer.",
				providerApiKey: "Hugging Face API key is required.",
				githubToken: "GitHub token is required.",
			},
		});
	});

	it("trims whitespace from the HF API key and GitHub token", () => {
		const result = validateReviewForm({
			...baseInput,
			providerApiKey: "  hf-key-with-spaces  ",
			githubToken: "  gh-token  ",
		});
		expect(result).toMatchObject({
			valid: true,
			value: {
				providerApiKey: "hf-key-with-spaces",
				githubToken: "gh-token",
			},
		});
	});
});
