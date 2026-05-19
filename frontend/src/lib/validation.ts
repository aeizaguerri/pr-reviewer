import type { ReviewRequest } from "../api/types";

export type ReviewFormInput = {
	repoSlug: string;
	prNumber: string;
	provider: string;
	providerApiKey: string;
	githubToken: string;
	model: string;
	baseUrlOverride: string;
};

export type ReviewFormErrors = Partial<Record<keyof ReviewFormInput, string>>;

export type ValidReviewForm = {
	request: ReviewRequest;
	providerApiKey: string;
	githubToken: string;
};

export type ValidationResult =
	| { valid: true; value: ValidReviewForm }
	| { valid: false; errors: ReviewFormErrors };

export function parseRepoSlug(
	repoSlug: string,
): { owner: string; repo: string } | null {
	const parts = repoSlug.trim().split("/");
	if (parts.length !== 2) {
		return null;
	}

	const [owner, repo] = parts.map((part) => part.trim());
	if (!owner || !repo) {
		return null;
	}

	return { owner, repo };
}

function providerAllowsEmptyApiKey(provider: string): boolean {
	return provider.trim().toLowerCase() === "ollama";
}

function backendProviderApiKey(
	provider: string,
	providerApiKey: string,
): string {
	if (providerAllowsEmptyApiKey(provider) && !providerApiKey) {
		return "ollama";
	}

	return providerApiKey;
}

export function validateReviewForm(input: ReviewFormInput): ValidationResult {
	const errors: ReviewFormErrors = {};
	const repoParts = parseRepoSlug(input.repoSlug);
	const prNumber = Number(input.prNumber);
	const provider = input.provider.trim();
	const providerApiKey = input.providerApiKey.trim();
	const githubToken = input.githubToken.trim();

	if (!repoParts) {
		errors.repoSlug = "Use the format owner/repo.";
	}

	if (!Number.isInteger(prNumber) || prNumber <= 0) {
		errors.prNumber = "PR number must be a positive integer.";
	}

	if (!provider) {
		errors.provider = "Choose a provider.";
	}

	if (provider && !providerAllowsEmptyApiKey(provider) && !providerApiKey) {
		errors.providerApiKey = "Provider API key is required.";
	}

	if (!githubToken) {
		errors.githubToken = "GitHub token is required.";
	}

	if (Object.keys(errors).length > 0 || !repoParts) {
		return { valid: false, errors };
	}

	return {
		valid: true,
		value: {
			request: {
				owner: repoParts.owner,
				repo: repoParts.repo,
				pr_number: prNumber,
				provider,
				model: input.model.trim(),
				base_url_override: input.baseUrlOverride.trim(),
			},
			providerApiKey: backendProviderApiKey(provider, providerApiKey),
			githubToken,
		},
	};
}
