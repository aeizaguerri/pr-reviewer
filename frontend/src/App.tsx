import { useEffect, useState } from "react";
import { getHealth, getProviders } from "./api/client";
import { AppError } from "./api/errors";
import type { HealthResponse, ProviderInfo, ReviewResponse } from "./api/types";
import { ReviewForm } from "./components/ReviewForm";
import { ReviewResults } from "./components/ReviewResults";
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
		return <p>Backend: checking...</p>;
	}

	if (state.status === "error") {
		return <p role="status">Backend unavailable — {state.message}</p>;
	}

	return <p>Backend: {state.data.status}</p>;
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
		<ul aria-label="Available providers">
			{state.data.map((provider) => (
				<li key={provider.key}>
					<strong>{provider.key}</strong> — {provider.description}
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
		<main className="app-shell">
			<section className="hero-card" aria-labelledby="app-title">
				<p className="eyebrow">React frontend scaffold</p>
				<h1 id="app-title">PR Code Reviewer</h1>
				<p>
					Docker-first Vite + React + TypeScript foundation for the production
					frontend.
				</p>
			</section>

			<section className="status-grid" aria-label="Backend and provider status">
				<article className="panel">
					<h2>Backend status</h2>
					<BackendStatus state={health} />
				</article>

				<article className="panel">
					<h2>Providers</h2>
					<ProviderList state={providers} />
				</article>
			</section>

			{providers.status === "success" ? (
				<section
					className="panel review-panel"
					aria-labelledby="review-form-title"
				>
					<h2 id="review-form-title">Run a PR review</h2>
					<ReviewForm
						providers={providers.data}
						onReviewComplete={setLatestReview}
					/>
					{latestReview ? <ReviewResults review={latestReview} /> : null}
				</section>
			) : null}
		</main>
	);
}
