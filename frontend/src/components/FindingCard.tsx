import type { FindingInput } from "../lib/displayModel";
import { CodeContextBlock } from "./CodeContextBlock";
import { SeverityPill } from "./SeverityPill";

type FindingCardProps = {
	finding: FindingInput;
};

export function FindingCard({ finding }: FindingCardProps) {
	return (
		<article className="finding-card">
			<div className="finding-card-header">
				<SeverityPill severity={finding.severity ?? ""} />
				{typeof finding.line === "number" ? (
					<span className="finding-line">Line {finding.line}</span>
				) : null}
			</div>
			<p className="finding-message">{finding.description}</p>
			<p className="finding-suggestion">{finding.suggestion}</p>
			<CodeContextBlock snippet={finding.source} />
		</article>
	);
}
