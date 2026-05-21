import type { ReviewHealth as ReviewHealthModel } from "../api/types";

type ReviewHealthProps = {
	health: ReviewHealthModel | null;
};

export function ReviewHealth({ health }: ReviewHealthProps) {
	if (!health || health.warnings.length === 0) {
		return null;
	}

	return (
		<section className="result-section" aria-labelledby="review-health-title">
			<h3 id="review-health-title">Review health: {health.status}</h3>
			<ul>
				{health.warnings.map((warning) => (
					<li key={warning}>{warning}</li>
				))}
			</ul>
		</section>
	);
}
