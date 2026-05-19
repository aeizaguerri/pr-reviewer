import { useState } from "react";
import { submitReview } from "../api/client";
import { AppError } from "../api/errors";
import type { ReviewResponse } from "../api/types";
import type { ValidReviewForm } from "../lib/validation";

type ReviewSubmissionState =
	| { status: "idle" }
	| { status: "loading" }
	| { status: "success"; data: ReviewResponse }
	| { status: "error"; message: string };

function sanitizedErrorMessage(error: unknown): string {
	if (error instanceof AppError) {
		return error.message;
	}
	return "Network error";
}

export function useReviewSubmission(
	onReviewComplete: (review: ReviewResponse) => void,
) {
	const [state, setState] = useState<ReviewSubmissionState>({ status: "idle" });

	async function runReview(input: ValidReviewForm): Promise<void> {
		setState({ status: "loading" });
		try {
			const review = await submitReview(input);
			setState({ status: "success", data: review });
			onReviewComplete(review);
		} catch (error) {
			setState({ status: "error", message: sanitizedErrorMessage(error) });
		}
	}

	return { state, runReview };
}
