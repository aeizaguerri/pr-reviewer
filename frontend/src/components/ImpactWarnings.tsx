import type { ImpactWarning } from "../api/types";

type ImpactWarningsProps = {
	warnings: ImpactWarning[];
};

export function ImpactWarnings({ warnings }: ImpactWarningsProps) {
	if (warnings.length === 0) {
		return null;
	}

	return (
		<section className="result-section" aria-labelledby="impact-warnings-title">
			<h3 id="impact-warnings-title">Impact warnings</h3>
			<ul className="card-list">
				{warnings.map((warning, index) => (
					<li
						key={`${warning.changed_file}-${warning.affected_service}-${index}`}
					>
						<strong>{warning.severity}</strong>: {warning.description}
						<dl className="metadata-list">
							<div>
								<dt>Changed file</dt>
								<dd>{warning.changed_file}</dd>
							</div>
							<div>
								<dt>Changed entity</dt>
								<dd>{warning.changed_entity}</dd>
							</div>
							<div>
								<dt>Affected service</dt>
								<dd>{warning.affected_service}</dd>
							</div>
							<div>
								<dt>Affected repository</dt>
								<dd>{warning.affected_repository}</dd>
							</div>
							<div>
								<dt>Relationship</dt>
								<dd>{warning.relationship_type}</dd>
							</div>
						</dl>
					</li>
				))}
			</ul>
		</section>
	);
}
