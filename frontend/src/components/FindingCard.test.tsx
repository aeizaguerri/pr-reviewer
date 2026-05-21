import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FindingCard } from "./FindingCard";
import type { FindingInput } from "../lib/displayModel";

describe("FindingCard", () => {
	const baseFinding: FindingInput = {
		file: "src/a.py",
		line: 10,
		severity: "major",
		description: "Logic error in loop",
		suggestion: "Use enumerate instead",
	};

	it("renders severity pill, line, message, and suggestion", () => {
		render(<FindingCard finding={baseFinding} />);
		expect(screen.getByText(/High severity/i)).toBeInTheDocument();
		expect(screen.getByText(/Line 10/i)).toBeInTheDocument();
		expect(screen.getByText("Logic error in loop")).toBeInTheDocument();
		expect(screen.getByText("Use enumerate instead")).toBeInTheDocument();
	});

	it("shows no-snippet fallback when snippet is absent", () => {
		render(<FindingCard finding={baseFinding} />);
		expect(screen.getByText(/no code snippet available/i)).toBeInTheDocument();
	});

	it("shows snippet when source is provided", () => {
		render(
			<FindingCard
				finding={{ ...baseFinding, source: "for i in range(len(items)):" }}
			/>,
		);
		expect(
			screen.getByText("for i in range(len(items)):"),
		).toBeInTheDocument();
	});

	it("handles missing line gracefully", () => {
		render(
			<FindingCard
				finding={{
					...baseFinding,
					line: undefined,
					description: "Missing line",
				}}
			/>,
		);
		expect(screen.getByText("Missing line")).toBeInTheDocument();
		expect(screen.queryByText(/Line \d+/i)).not.toBeInTheDocument();
	});
});
