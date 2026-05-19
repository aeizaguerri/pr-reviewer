import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppError } from "../api/errors";
import type { ProviderInfo } from "../api/types";
import { ReviewForm } from "./ReviewForm";
import { submitReview } from "../api/client";

vi.mock("../api/client", () => ({
	submitReview: vi.fn(),
}));

const providers: ProviderInfo[] = [
	{
		key: "cerebras",
		description: "Fast hosted model",
		default_model: "llama-3.3-70b",
		key_label: "Cerebras API Key",
		supports_structured_output: true,
	},
	{
		key: "ollama",
		description: "Local Ollama server",
		default_model: "llama3.2",
		key_label: "Ollama API Key",
		supports_structured_output: false,
	},
];

function submitReviewMock() {
	return vi.mocked(submitReview);
}

function providerSelect() {
	return screen.getByLabelText(/^provider$/i);
}

async function fillValidForm() {
	const user = userEvent.setup();
	await user.selectOptions(providerSelect(), "cerebras");
	await user.type(
		screen.getByLabelText(/repository/i),
		"gentleman-programming/pr-reviewer",
	);
	await user.type(screen.getByLabelText(/pull request number/i), "42");
	await user.type(
		screen.getByLabelText(/provider api key/i),
		"provider-secret",
	);
	await user.type(screen.getByLabelText(/github token/i), "github-secret");
	return user;
}

describe("ReviewForm", () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	it("renders provider options, model hint, and masked secret inputs", async () => {
		render(<ReviewForm providers={providers} onReviewComplete={vi.fn()} />);

		await userEvent.selectOptions(providerSelect(), "cerebras");

		expect(
			screen.getByRole("option", { name: /cerebras — fast hosted model/i }),
		).toBeInTheDocument();
		expect(
			screen.getByText(/default model: llama-3.3-70b/i),
		).toBeInTheDocument();
		expect(screen.getByLabelText(/provider api key/i)).toHaveAttribute(
			"type",
			"password",
		);
		expect(screen.getByLabelText(/github token/i)).toHaveAttribute(
			"type",
			"password",
		);
	});

	it("keeps submit disabled for invalid input and displays validation errors", async () => {
		const user = userEvent.setup();
		render(<ReviewForm providers={providers} onReviewComplete={vi.fn()} />);

		expect(screen.getByRole("button", { name: /run review/i })).toBeDisabled();

		await user.selectOptions(providerSelect(), "cerebras");
		await user.type(screen.getByLabelText(/repository/i), "owner/");
		await user.type(screen.getByLabelText(/pull request number/i), "0");
		await user.click(screen.getByRole("button", { name: /run review/i }));

		expect(screen.getByText(/use the format owner\/repo/i)).toBeInTheDocument();
		expect(
			screen.getByText(/pr number must be a positive integer/i),
		).toBeInTheDocument();
		expect(
			screen.getByText(/provider api key is required/i),
		).toBeInTheDocument();
		expect(screen.getByText(/github token is required/i)).toBeInTheDocument();
		expect(submitReviewMock()).not.toHaveBeenCalled();
	});

	it("submits parsed review input and never persists secrets in browser storage", async () => {
		const storageSetItem = vi.spyOn(Storage.prototype, "setItem");
		const onReviewComplete = vi.fn();
		submitReviewMock().mockResolvedValue({
			summary: "Review queued",
			approved: true,
			bugs: [],
			impact_warnings: [],
			review_health: null,
		});
		render(
			<ReviewForm providers={providers} onReviewComplete={onReviewComplete} />,
		);

		const user = await fillValidForm();
		await user.type(screen.getByLabelText(/model override/i), "custom-model");
		await user.type(
			screen.getByLabelText(/base url override/i),
			" http://backend:11434/v1 ",
		);
		await user.click(screen.getByRole("button", { name: /run review/i }));

		await waitFor(() => expect(submitReviewMock()).toHaveBeenCalledTimes(1));
		expect(submitReviewMock()).toHaveBeenCalledWith({
			request: {
				owner: "gentleman-programming",
				repo: "pr-reviewer",
				pr_number: 42,
				provider: "cerebras",
				model: "custom-model",
				base_url_override: "http://backend:11434/v1",
			},
			providerApiKey: "provider-secret",
			githubToken: "github-secret",
		});
		await waitFor(() =>
			expect(onReviewComplete).toHaveBeenCalledWith(
				expect.objectContaining({ summary: "Review queued" }),
			),
		);
		expect(storageSetItem).not.toHaveBeenCalled();
	});

	it("shows loading copy and disables submit while a review is running", async () => {
		submitReviewMock().mockImplementation(() => new Promise(() => undefined));
		render(<ReviewForm providers={providers} onReviewComplete={vi.fn()} />);

		const user = await fillValidForm();
		await user.click(screen.getByRole("button", { name: /run review/i }));

		expect(
			screen.getByRole("button", { name: /running review/i }),
		).toBeDisabled();
		expect(
			screen.getByText(/reviews can take several minutes/i),
		).toBeInTheDocument();
	});

	it("displays sanitized AppError messages without leaking secrets", async () => {
		submitReviewMock().mockRejectedValue(
			new AppError("auth", "401 Unauthorized"),
		);
		render(<ReviewForm providers={providers} onReviewComplete={vi.fn()} />);

		const user = await fillValidForm();
		await user.click(screen.getByRole("button", { name: /run review/i }));

		await waitFor(() =>
			expect(screen.getByRole("alert")).toHaveTextContent("401 Unauthorized"),
		);
		expect(screen.queryByText(/provider-secret/i)).not.toBeInTheDocument();
		expect(screen.queryByText(/github-secret/i)).not.toBeInTheDocument();
	});
});
