import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SeverityPill } from "./SeverityPill";

describe("SeverityPill", () => {
	it("renders a text label for Critical severity", () => {
		render(<SeverityPill severity="Critical" />);
		expect(screen.getByText(/Critical severity/i)).toBeInTheDocument();
	});

	it("renders a text label for High severity", () => {
		render(<SeverityPill severity="High" />);
		expect(screen.getByText(/High severity/i)).toBeInTheDocument();
	});

	it("renders a text label for Medium severity", () => {
		render(<SeverityPill severity="Medium" />);
		expect(screen.getByText(/Medium severity/i)).toBeInTheDocument();
	});

	it("renders a text label for Low severity", () => {
		render(<SeverityPill severity="Low" />);
		expect(screen.getByText(/Low severity/i)).toBeInTheDocument();
	});

	it("renders Unknown for unrecognized severity", () => {
		render(<SeverityPill severity="info" />);
		expect(screen.getByText(/Unknown severity/i)).toBeInTheDocument();
	});

	it("exposes severity as a data attribute", () => {
		render(<SeverityPill severity="Critical" />);
		const pill = screen.getByText(/Critical severity/i).closest("span");
		expect(pill).toHaveAttribute("data-severity", "Critical");
	});
});
