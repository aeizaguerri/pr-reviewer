import { AppError, categoryForStatus } from "./errors";
import type {
	HealthResponse,
	ProvidersResponse,
	ReviewRequest,
	ReviewResponse,
} from "./types";

function apiBaseUrl(): string {
	const runtimeBaseUrl = window.__PR_REVIEWER_CONFIG__?.apiBaseUrl?.trim();
	if (runtimeBaseUrl) {
		return runtimeBaseUrl;
	}

	return import.meta.env.VITE_API_BASE_URL ?? "";
}

function endpoint(path: string): string {
	return `${apiBaseUrl()}${path}`;
}

async function parseJson<T>(response: Response): Promise<T> {
	if (!response.ok) {
		throw new AppError(
			categoryForStatus(response.status),
			`${response.status} ${response.statusText || "API request failed"}`,
			response.status,
		);
	}

	return (await response.json()) as T;
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
	try {
		const response = await fetch(endpoint(path), init);
		return await parseJson<T>(response);
	} catch (error) {
		if (error instanceof AppError) {
			throw error;
		}
		throw new AppError("network", "Network error");
	}
}

export function getHealth(): Promise<HealthResponse> {
	return requestJson<HealthResponse>("/health", {
		method: "GET",
		headers: { Accept: "application/json" },
	});
}

export function getProviders(): Promise<ProvidersResponse> {
	return requestJson<ProvidersResponse>("/api/v1/providers", {
		method: "GET",
		headers: { Accept: "application/json" },
	});
}

export function submitReview(input: {
	request: ReviewRequest;
	providerApiKey: string;
	githubToken: string;
}): Promise<ReviewResponse> {
	return requestJson<ReviewResponse>("/api/v1/review", {
		method: "POST",
		headers: {
			Accept: "application/json",
			Authorization: `Bearer ${input.providerApiKey}`,
			"Content-Type": "application/json",
			"X-GitHub-Token": input.githubToken,
		},
		body: JSON.stringify(input.request),
	});
}
