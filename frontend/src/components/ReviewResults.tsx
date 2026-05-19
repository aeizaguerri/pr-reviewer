import type { ReviewResponse } from "../api/types";
import { buildReviewDisplay } from "../lib/displayModel";
import { FindingsTable } from "./FindingsTable";
import { ImpactWarnings } from "./ImpactWarnings";
import { ReviewHealth } from "./ReviewHealth";

type ReviewResultsProps = {
	review: ReviewResponse;
};

export function ReviewResults({ review }: ReviewResultsProps) {
	const display = buildReviewDisplay(review);

	return (
		<section className="review-results" aria-labelledby="review-result-title">
			<div className="result-header">
				<div>
					<p className="eyebrow">Review result</p>
					<h2 id="review-result-title">Review result</h2>
				</div>
				<div className="approval-badge" data-approved={display.approved}>
					<strong>{display.approvalLabel}</strong>
					<span>{display.approvalDelta}</span>
				</div>
			</div>

			{display.summary ? <p>{display.summary}</p> : null}

			<FindingsTable
				id="bug-findings"
				title="Bug findings"
				rows={display.bugRows}
			/>
			<FindingsTable
				id="security-findings"
				title="Security findings"
				rows={display.securityRows}
			/>
			<ImpactWarnings warnings={display.impactWarnings} />
			<ReviewHealth health={display.health} />
		</section>
	);
}
