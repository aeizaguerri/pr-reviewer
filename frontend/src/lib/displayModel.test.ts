import { describe, expect, it } from "vitest";
import {
	buildReviewDisplay,
	formatBugRow,
	formatReviewHealth,
	groupFindingsByCategory,
} from "./displayModel";

describe("groupFindingsByCategory", () => {
	it("groups findings by explicit bug and security categories", () => {
		const groups = groupFindingsByCategory([
			{ file: "a.py", line: 1, category: "bug", severity: "major" },
			{ file: "b.py", line: 2, category: "security", severity: "critical" },
			{ file: "c.py", line: 3, category: "bug", severity: "minor" },
		]);

		expect(groups.bug).toHaveLength(2);
		expect(groups.security).toHaveLength(1);
		expect(groups.security[0]).toMatchObject({ file: "b.py" });
	});

	it("defaults missing and empty categories to bug", () => {
		const groups = groupFindingsByCategory([
			{ file: "missing.py", line: 1, severity: "major" },
			{ file: "empty.py", line: 2, category: "", severity: "minor" },
			{
				file: "secure.py",
				line: 3,
				category: "security",
				severity: "critical",
			},
		]);

		expect(groups.bug.map((bug) => bug.file)).toEqual([
			"missing.py",
			"empty.py",
		]);
		expect(groups.security.map((bug) => bug.file)).toEqual(["secure.py"]);
	});
});

describe("formatBugRow", () => {
	it("formats key fields and major severity emoji", () => {
		expect(
			formatBugRow({
				file: "src/a.py",
				line: 10,
				severity: "major",
				description: "logic error",
				suggestion: "fix it",
			}),
		).toEqual({
			Severity: "🟠 major",
			File: "src/a.py",
			Line: 10,
			Description: "logic error",
			Suggestion: "fix it",
		});
	});

	it("formats critical and minor severity emoji while preserving unknown severities", () => {
		expect(formatBugRow({ severity: "critical" }).Severity).toBe("🔴 critical");
		expect(formatBugRow({ severity: "minor" }).Severity).toBe("🟡 minor");
		expect(formatBugRow({ severity: "info" }).Severity).toBe("info");
	});
});

describe("formatReviewHealth", () => {
	it("normalizes populated review health", () => {
		expect(
			formatReviewHealth({
				status: "partial",
				warnings: ["cross-repo skipped"],
			}),
		).toEqual({ status: "partial", warnings: ["cross-repo skipped"] });
	});

	it("returns null when absent and defaults minimal health", () => {
		expect(formatReviewHealth(null)).toBeNull();
		expect(formatReviewHealth({})).toEqual({
			status: "complete",
			warnings: [],
		});
	});
});

describe("buildReviewDisplay", () => {
	it("builds all sections for mixed findings", () => {
		const display = buildReviewDisplay({
			approved: false,
			summary: "Found issues",
			bugs: [
				{
					file: "a.py",
					line: 1,
					severity: "major",
					description: "d1",
					suggestion: "s1",
					category: "bug",
				},
				{
					file: "b.py",
					line: 2,
					severity: "critical",
					description: "d2",
					suggestion: "s2",
					category: "security",
				},
			],
			impact_warnings: [
				{
					changed_file: "c.py",
					changed_entity: "handler",
					affected_service: "svc",
					affected_repository: "repo",
					relationship_type: "calls",
					severity: "high",
					description: "breaks",
				},
			],
			review_health: { status: "partial", warnings: ["cross-repo skipped"] },
		});

		expect(display.approved).toBe(false);
		expect(display.approvalLabel).toBe("❌ Changes Requested");
		expect(display.approvalDelta).toBe("Requires changes");
		expect(display.summary).toBe("Found issues");
		expect(display.health).toEqual({
			status: "partial",
			warnings: ["cross-repo skipped"],
		});
		expect(display.bugRows).toHaveLength(1);
		expect(display.bugRows[0].File).toBe("a.py");
		expect(display.securityRows).toHaveLength(1);
		expect(display.securityRows[0].File).toBe("b.py");
		expect(display.impactWarnings).toHaveLength(1);
		expect(display.impactWarnings[0].changed_file).toBe("c.py");
	});

	it("builds clean approved display with no noisy finding sections", () => {
		const display = buildReviewDisplay({
			approved: true,
			summary: "No bugs detected.",
			bugs: [],
			impact_warnings: [],
			review_health: { status: "complete", warnings: [] },
		});

		expect(display.approvalLabel).toBe("✅ Approved");
		expect(display.approvalDelta).toBe("Ready to merge");
		expect(display.bugRows).toEqual([]);
		expect(display.securityRows).toEqual([]);
		expect(display.impactWarnings).toEqual([]);
	});

	it("keeps absent review health absent", () => {
		const display = buildReviewDisplay({
			approved: true,
			summary: "Clean",
			bugs: [],
			impact_warnings: [],
		});

		expect(display.health).toBeNull();
	});
});
