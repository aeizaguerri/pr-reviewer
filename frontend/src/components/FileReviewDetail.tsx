import type { FileFindingGroup } from "../lib/displayModel";
import { FindingCard } from "./FindingCard";

type FileReviewDetailProps = {
	group: FileFindingGroup;
};

export function FileReviewDetail({ group }: FileReviewDetailProps) {
	return (
		<section className="file-detail" aria-label={`Findings for ${group.fileLabel}`}>
			<div className="file-detail-header">
				<h2 className="file-detail-heading">{group.fileLabel}</h2>
				<span className="finding-line">
					{group.findings.length} finding
					{group.findings.length === 1 ? "" : "s"}
				</span>
			</div>

			{group.findings.length === 0 ? (
				<p className="file-detail-empty">No findings — this file looks clean.</p>
			) : (
				group.findings.map((finding, index) => (
					<FindingCard key={index} finding={finding} />
				))
			)}
		</section>
	);
}
