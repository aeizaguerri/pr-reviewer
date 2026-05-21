import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FileReviewDetail } from "./FileReviewDetail";
import type { FileFindingGroup } from "../lib/displayModel";

describe("FileReviewDetail", () => {
	const group: FileFindingGroup = {
		key: "a.py",
		fileLabel: "a.py",
		findings: [
			{ file: "a.py", line: 1, severity: "major", description: "d1", suggestion: "s1" },
			{ file: "a.py", line: 5, severity: "critical", description: "d2", suggestion: "s2" },
		],
		counts: { major: 1, critical: 1 },
		firstLine: 1,
	};

	it("renders selected file heading and finding count", () => {
		render(<FileReviewDetail group={group} />);
		expect(screen.getByRole("heading", { name: /a\.py/i })).toBeInTheDocument();
		expect(screen.getByText(/2 findings/i)).toBeInTheDocument();
	});

	it("renders finding cards for each finding", () => {
		render(<FileReviewDetail group={group} />);
		expect(screen.getByText("d1")).toBeInTheDocument();
		expect(screen.getByText("d2")).toBeInTheDocument();
	});

	it("shows clean state for empty group", () => {
		render(
			<FileReviewDetail
				group={{
					key: "clean.py",
					fileLabel: "clean.py",
					findings: [],
					counts: {},
					firstLine: null,
				}}
			/>,
		);
		expect(screen.getByText(/no findings/i)).toBeInTheDocument();
	});
});
