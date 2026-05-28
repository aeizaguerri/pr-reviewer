import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppError } from "../api/errors";
import { ReviewForm } from "./ReviewForm";
import { submitReview } from "../api/client";

vi.mock("../api/client", () => ({
	submitReview: vi.fn(),
}));

function submitReviewMock() {
	return vi.mocked(submitReview);
}

async function fillValidForm() {
	const user = userEvent.setup();
	await user.type(
		screen.getByLabelText(/repository/i),
		"gentleman-programming/pr-reviewer",
	);
	await user.type(screen.getByLabelText(/pull request number/i), "42");
	await user.type(
		screen.getByLabelText(/hugging face api key/i),
		"hf-secret",
	);
	await user.type(screen.getByLabelText(/github token/i), "github-secret");
	return user;
}

describe("ReviewForm", () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	it("renders only the four curated fields and masked secret inputs", async () => {
		render(<ReviewForm onReviewComplete={vi.fn()} />);

		expect(screen.getByLabelText(/repository/i)).toBeInTheDocument();
		expect(
			screen.getByLabelText(/pull request number/i),
		).toBeInTheDocument();
		expect(
			screen.getByLabelText(/hugging face api key/i),
		).toBeInTheDocument();
		expect(screen.getByLabelText(/github token/i)).toBeInTheDocument();

		// Removed controls must not be in the DOM
		expect(screen.queryByLabelText(/^provider$/i)).not.toBeInTheDocument();
		expect(
			screen.queryByLabelText(/model override/i),
		).not.toBeInTheDocument();
		expect(
			screen.queryByLabelText(/base url override/i),
		).not.toBeInTheDocument();

		// Secrets are masked
		expect(screen.getByLabelText(/hugging face api key/i)).toHaveAttribute(
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
		render(<ReviewForm onReviewComplete={vi.fn()} />);

		expect(screen.getByRole("button", { name: /run review/i })).toBeDisabled();

		await user.type(screen.getByLabelText(/repository/i), "owner/");
		await user.type(screen.getByLabelText(/pull request number/i), "0");
		await user.click(screen.getByRole("button", { name: /run review/i }));

		expect(screen.getByText(/use the format owner\/repo/i)).toBeInTheDocument();
		expect(
			screen.getByText(/pr number must be a positive integer/i),
		).toBeInTheDocument();
		expect(
			screen.getByText(/hugging face api key is required/i),
		).toBeInTheDocument();
		expect(screen.getByText(/github token is required/i)).toBeInTheDocument();
		expect(submitReviewMock()).not.toHaveBeenCalled();
	});

	it("submits parsed review input with HF-only payload and never persists secrets in browser storage", async () => {
		const storageSetItem = vi.spyOn(Storage.prototype, "setItem");
		const onReviewComplete = vi.fn();
		submitReviewMock().mockResolvedValue({
			summary: "Review queued",
			approved: true,
			bugs: [],
			impact_warnings: [],
			review_health: null,
		});
		render(<ReviewForm onReviewComplete={onReviewComplete} />);

		const user = await fillValidForm();
		await user.click(screen.getByRole("button", { name: /run review/i }));

		await waitFor(() => expect(submitReviewMock()).toHaveBeenCalledTimes(1));
		expect(submitReviewMock()).toHaveBeenCalledWith({
			request: {
				owner: "gentleman-programming",
				repo: "pr-reviewer",
				pr_number: 42,
			},
			providerApiKey: "hf-secret",
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
		render(<ReviewForm onReviewComplete={vi.fn()} />);

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
		render(<ReviewForm onReviewComplete={vi.fn()} />);

		const user = await fillValidForm();
		await user.click(screen.getByRole("button", { name: /run review/i }));

		await waitFor(() =>
			expect(screen.getByRole("alert")).toHaveTextContent("401 Unauthorized"),
		);
		expect(screen.queryByText(/hf-secret/i)).not.toBeInTheDocument();
		expect(screen.queryByText(/github-secret/i)).not.toBeInTheDocument();
	});
});
