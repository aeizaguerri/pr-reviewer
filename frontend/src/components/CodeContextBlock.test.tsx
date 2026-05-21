import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CodeContextBlock } from "./CodeContextBlock";

describe("CodeContextBlock", () => {
	it("renders snippet in monospace when provided", () => {
		render(<CodeContextBlock snippet="const x = 1;" language="typescript" />);
		const block = screen.getByText("const x = 1;");
		expect(block).toBeInTheDocument();
		expect(block.tagName).toBe("PRE");
	});

	it("shows no-snippet placeholder when snippet is absent", () => {
		render(<CodeContextBlock />);
		expect(screen.getByText(/no code snippet available/i)).toBeInTheDocument();
	});

	it("shows no-snippet placeholder when snippet is blank", () => {
		render(<CodeContextBlock snippet="   " />);
		expect(screen.getByText(/no code snippet available/i)).toBeInTheDocument();
	});
});
