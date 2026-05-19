import type { FindingRow } from "../lib/displayModel";

type FindingsTableProps = {
	id: string;
	title: string;
	rows: FindingRow[];
};

export function FindingsTable({ id, title, rows }: FindingsTableProps) {
	if (rows.length === 0) {
		return null;
	}

	const titleId = `${id}-title`;

	return (
		<section className="result-section" aria-labelledby={titleId}>
			<h3 id={titleId}>{title}</h3>
			<div className="table-scroll">
				<table aria-label={title}>
					<thead>
						<tr>
							<th scope="col">Severity</th>
							<th scope="col">File</th>
							<th scope="col">Line</th>
							<th scope="col">Description</th>
							<th scope="col">Suggestion</th>
						</tr>
					</thead>
					<tbody>
						{rows.map((row, index) => (
							<tr key={`${row.File}-${row.Line}-${index}`}>
								<td>{row.Severity}</td>
								<td>{row.File}</td>
								<td>{row.Line}</td>
								<td>{row.Description}</td>
								<td>{row.Suggestion}</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</section>
	);
}
