import { useEffect, useState } from "react";
import { getHealth, getProviders } from "./api/client";
import { AppError } from "./api/errors";
import type { HealthResponse, ProviderInfo, ReviewResponse } from "./api/types";
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

function ProviderList({ state }: { state: AsyncState<ProviderInfo[]> }) {
	if (state.status === "loading") {
		return <p>Loading providers...</p>;
	}

	if (state.status === "error") {
		return <p role="status">Providers unavailable — {state.message}</p>;
	}

	if (state.data.length === 0) {
		return <p>No providers available yet.</p>;
	}

	return (
		<ul className="provider-list" aria-label="Available providers">
			{state.data.map((provider) => (
				<li key={provider.key}>
					<span className="provider-key">{provider.key}</span>
					<span className="provider-description">{provider.description}</span>
				</li>
			))}
		</ul>
	);
}

export default function App() {
	const [health, setHealth] = useState<AsyncState<HealthResponse>>({
		status: "loading",
	});
	const [providers, setProviders] = useState<AsyncState<ProviderInfo[]>>({
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

		getProviders()
			.then((data) => {
				if (active) {
					setProviders({ status: "success", data: data.providers });
				}
			})
			.catch((error: unknown) => {
				if (active) {
					setProviders({ status: "error", message: errorMessage(error) });
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
						<section className="sidebar-section" aria-label="Backend and provider status">
							<div className="sidebar-section-header">
								<h2>Backend status</h2>
							</div>
							<div className="sidebar-section-body">
								<BackendStatus state={health} />
							</div>
						</section>

						<section className="sidebar-section" aria-label="Providers">
							<div className="sidebar-section-header">
								<h2>Providers</h2>
							</div>
							<div className="sidebar-section-body">
								<ProviderList state={providers} />
							</div>
						</section>

						{providers.status === "success" ? (
							<section
								className="sidebar-section"
								aria-labelledby="review-form-title"
							>
								<div className="sidebar-section-header">
									<h2 id="review-form-title">Run a PR review</h2>
								</div>
								<div className="sidebar-section-body">
									<ReviewForm
										providers={providers.data}
										onReviewComplete={setLatestReview}
									/>
								</div>
							</section>
						) : null}
					</>
				}
		/>
	);
}
