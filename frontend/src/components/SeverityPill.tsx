type SeverityPillProps = {
	severity: string;
};

const severityLabel: Record<string, string> = {
	critical: "Critical",
	major: "High",
	high: "High",
	minor: "Medium",
	medium: "Medium",
	low: "Low",
};

const severityIcon: Record<string, string> = {
	Critical: "!",
	High: "!",
	Medium: "~",
	Low: "·",
	Unknown: "?",
};

export function SeverityPill({ severity }: SeverityPillProps) {
	const normalized = severity.toLowerCase();
	const label = severityLabel[normalized] ?? "Unknown";
	const icon = severityIcon[label];

	return (
		<span className="severity-pill" data-severity={label}>
			<span aria-hidden="true">{icon}</span>
			{label} severity
		</span>
	);
}
