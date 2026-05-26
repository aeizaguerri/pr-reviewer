import { useEffect, useState } from "react";
import { getHealth } from "./api/client";
import { AppError } from "./api/errors";
import type { HealthResponse, ReviewResponse } from "./api/types";
import { ReviewForm } from "./components/ReviewForm";
import { WorkspaceShell } from "./components/WorkspaceShell";
import "./styles/global.css";

type AsyncState<T> =
	| { status: "loading" }
	| { status: "success"; data: T }
	| { status: "error"; message: string };

function errorMessage(error: unknown): string {
	if (error instanceof AppError) {
		return error.message;
	}
	return "Network error";
}

function BackendStatus({ state }: { state: AsyncState<HealthResponse> }) {
	if (state.status === "loading") {
		return <p className="status-line">Checking backend...</p>;
	}

	if (state.status === "error") {
		return <p className="status-line" role="status">Backend unavailable — {state.message}</p>;
	}

	return <p className="status-line">Backend: {state.data.status}</p>;
}

export default function App() {
	const [health, setHealth] = useState<AsyncState<HealthResponse>>({
		status: "loading",
	});
	const [latestReview, setLatestReview] = useState<ReviewResponse | null>(null);

	useEffect(() => {
		let active = true;

		getHealth()
			.then((data) => {
				if (active) {
					setHealth({ status: "success", data });
				}
			})
			.catch((error: unknown) => {
				if (active) {
					setHealth({ status: "error", message: errorMessage(error) });
				}
			});

		return () => {
			active = false;
		};
	}, []);

	return (
		<WorkspaceShell
			latestReview={latestReview}
			sidebar={
				<>
					<section className="sidebar-section" aria-label="Backend status">
						<div className="sidebar-section-header">
							<h2>Backend status</h2>
						</div>
						<div className="sidebar-section-body">
							<BackendStatus state={health} />
						</div>
					</section>

					{health.status === "success" ? (
						<section
							className="sidebar-section"
							aria-labelledby="review-form-title"
						>
							<div className="sidebar-section-header">
								<h2 id="review-form-title">Run a PR review</h2>
							</div>
							<div className="sidebar-section-body">
								<ReviewForm onReviewComplete={setLatestReview} />
							</div>
						</section>
					) : null}
				</>
			}
		/>
	);
}
