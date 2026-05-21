import type { ImpactWarning, ReviewHealth, ReviewResponse } from "../api/types";

export type FindingInput = {
	file?: string;
	line?: number;
	severity?: string;
	description?: string;
	suggestion?: string;
	source?: string;
	category?: string | null;
};

export type FindingRow = {
	Severity: string;
	File: string;
	Line: number;
	Description: string;
	Suggestion: string;
};

export type ReviewDisplay = {
	approved: boolean;
	approvalLabel: string;
	approvalDelta: string;
	summary: string;
	health: ReviewHealth | null;
	bugRows: FindingRow[];
	securityRows: FindingRow[];
	impactWarnings: ImpactWarning[];
};

export type FileFindingGroup = {
	key: string;
	fileLabel: string;
	findings: FindingInput[];
	counts: Record<string, number>;
	firstLine: number | null;
};

export type ReviewWorkspaceDisplay = {
	groups: FileFindingGroup[];
	selectedFileKey: string | null;
};

type ReviewDisplayInput = Partial<Omit<ReviewResponse, "bugs">> & {
	bugs?: FindingInput[];
};

const severityEmoji: Record<string, string> = {
	critical: "🔴",
	major: "🟠",
	minor: "🟡",
};

function findingCategory(finding: FindingInput): string {
	return finding.category || "bug";
}

export function groupFindingsByCategory(
	findings: FindingInput[],
): Record<string, FindingInput[]> {
	return findings.reduce<Record<string, FindingInput[]>>((groups, finding) => {
		const category = findingCategory(finding);
		groups[category] = [...(groups[category] ?? []), finding];
		return groups;
	}, {});
}

export function formatBugRow(finding: FindingInput): FindingRow {
	const severity = finding.severity ?? "";
	const emoji = severityEmoji[severity] ?? "";

	return {
		Severity: `${emoji} ${severity}`.trim(),
		File: finding.file ?? "",
		Line: finding.line ?? 0,
		Description: finding.description ?? "",
		Suggestion: finding.suggestion ?? "",
	};
}

export function formatReviewHealth(
	health: Partial<ReviewHealth> | null | undefined,
): ReviewHealth | null {
	if (health == null) {
		return null;
	}

	return {
		status: health.status ?? "complete",
		warnings: [...(health.warnings ?? [])],
	};
}

export function groupFindingsByFile(findings: FindingInput[]): FileFindingGroup[] {
	const map = new Map<string, FindingInput[]>();

	for (const finding of findings) {
		const rawFile = finding.file ?? "";
		const key = rawFile.trim() === "" ? "__unknown_file__" : rawFile;
		const existing = map.get(key) ?? [];
		map.set(key, [...existing, finding]);
	}

	const entries = Array.from(map.entries());
	entries.sort(([a], [b]) => {
		if (a === "__unknown_file__") return 1;
		if (b === "__unknown_file__") return -1;
		return a.localeCompare(b);
	});

	return entries.map(([key, groupFindings]) => {
		const counts: Record<string, number> = {};
		let firstLine: number | null = null;
		for (const f of groupFindings) {
			const sev = f.severity ?? "Unknown";
			counts[sev] = (counts[sev] ?? 0) + 1;
			if (typeof f.line === "number") {
				if (firstLine === null || f.line < firstLine) {
					firstLine = f.line;
				}
			}
		}
		return {
			key,
			fileLabel: key === "__unknown_file__" ? "Unknown file" : key,
			findings: groupFindings,
			counts,
			firstLine,
		};
	});
}

export function buildReviewWorkspaceDisplay(
	review: { bugs?: FindingInput[] },
): ReviewWorkspaceDisplay {
	const groups = groupFindingsByFile(review.bugs ?? []);
	return {
		groups,
		selectedFileKey: groups.length > 0 ? groups[0].key : null,
	};
}

export function buildReviewDisplay(result: ReviewDisplayInput): ReviewDisplay {
	const approved = result.approved ?? false;
	const groups = groupFindingsByCategory(result.bugs ?? []);

	return {
		approved,
		approvalLabel: approved ? "✅ Approved" : "❌ Changes Requested",
		approvalDelta: approved ? "Ready to merge" : "Requires changes",
		summary: result.summary ?? "",
		health: formatReviewHealth(result.review_health),
		bugRows: (groups.bug ?? []).map(formatBugRow),
		securityRows: (groups.security ?? []).map(formatBugRow),
		impactWarnings: result.impact_warnings ?? [],
	};
}
