import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ReviewResponse } from "../api/types";
import { ReviewResults } from "./ReviewResults";

const cleanReview: ReviewResponse = {
	summary: "No bugs detected.",
	approved: true,
	bugs: [],
	impact_warnings: [],
	review_health: { status: "complete", warnings: [] },
};

const mixedReview: ReviewResponse = {
	summary: "Found issues",
	approved: false,
	bugs: [
		{
			file: "src/bug.py",
			line: 12,
			severity: "major",
			description: "Bug finding",
			suggestion: "Fix the branch",
			category: "bug",
			source: "reviewer",
		},
		{
			file: "src/security.py",
			line: 4,
			severity: "critical",
			description: "Security finding",
			suggestion: "Validate input",
			category: "security",
			source: "security",
		},
	],
	impact_warnings: [
		{
			severity: "high",
			description: "Could break the billing service",
			changed_file: "src/api.py",
			changed_entity: "create_invoice",
			affected_service: "billing",
			affected_repository: "payments",
			relationship_type: "calls",
		},
	],
	review_health: { status: "partial", warnings: ["cross-repo skipped"] },
};

describe("ReviewResults", () => {
	it("renders clean approved review without noisy empty sections", () => {
		render(<ReviewResults review={cleanReview} />);

		expect(
			screen.getByRole("heading", { name: /review result/i }),
		).toBeInTheDocument();
		expect(screen.getByText("✅ Approved")).toBeInTheDocument();
		expect(screen.getByText("Ready to merge")).toBeInTheDocument();
		expect(screen.getByText("No bugs detected.")).toBeInTheDocument();
		expect(screen.queryByRole("table", { name: /bug findings/i })).toBeNull();
		expect(
			screen.queryByRole("table", { name: /security findings/i }),
		).toBeNull();
		expect(screen.queryByText(/impact warnings/i)).not.toBeInTheDocument();
	});

	it("renders changes requested with bug and security finding tables", () => {
		render(<ReviewResults review={mixedReview} />);

		expect(screen.getByText("❌ Changes Requested")).toBeInTheDocument();
		expect(screen.getByText("Requires changes")).toBeInTheDocument();

		expect(document.getElementById("Bug findings-title")).toBeNull();
		expect(document.getElementById("bug-findings-title")).toHaveTextContent(
			"Bug findings",
		);

		const bugTable = screen.getByRole("table", { name: /bug findings/i });
		expect(within(bugTable).getByText("src/bug.py")).toBeInTheDocument();
		expect(within(bugTable).getByText("🟠 major")).toBeInTheDocument();
		expect(within(bugTable).getByText("Bug finding")).toBeInTheDocument();

		const securityTable = screen.getByRole("table", {
			name: /security findings/i,
		});
		expect(
			within(securityTable).getByText("src/security.py"),
		).toBeInTheDocument();
		expect(within(securityTable).getByText("🔴 critical")).toBeInTheDocument();
		expect(
			within(securityTable).getByText("Security finding"),
		).toBeInTheDocument();
	});

	it("renders impact warnings and review health warnings", () => {
		render(<ReviewResults review={mixedReview} />);

		expect(
			screen.getByRole("heading", { name: /impact warnings/i }),
		).toBeInTheDocument();
		expect(
			screen.getByText(/Could break the billing service/),
		).toBeInTheDocument();
		expect(screen.getByText(/src\/api.py/)).toBeInTheDocument();
		expect(screen.getAllByText("billing").length).toBeGreaterThan(0);

		expect(screen.getByText(/review health: partial/i)).toBeInTheDocument();
		expect(screen.getByText("cross-repo skipped")).toBeInTheDocument();
	});
});
