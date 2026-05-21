import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FileReviewNavigator } from "./FileReviewNavigator";
import type { FileFindingGroup } from "../lib/displayModel";

describe("FileReviewNavigator", () => {
	const groups: FileFindingGroup[] = [
		{
			key: "a.py",
			fileLabel: "a.py",
			findings: [{ file: "a.py", line: 1, severity: "major", description: "d1" }],
			counts: { major: 1 },
			firstLine: 1,
		},
		{
			key: "__unknown_file__",
			fileLabel: "Unknown file",
			findings: [{ line: 2, severity: "critical", description: "d2" }],
			counts: { critical: 1 },
			firstLine: 2,
		},
	];

	it("renders file groups as buttons with counts", () => {
		render(
			<FileReviewNavigator
				groups={groups}
				selectedKey="a.py"
				onSelect={() => undefined}
			/>,
		);

		expect(screen.getByRole("button", { name: /a\.py/i })).toBeInTheDocument();
		expect(
			screen.getByRole("button", { name: /Unknown file/i }),
		).toBeInTheDocument();
	});

	it("marks selected button with aria-current", () => {
		render(
			<FileReviewNavigator
				groups={groups}
				selectedKey="a.py"
				onSelect={() => undefined}
			/>,
		);

		const selected = screen.getByRole("button", { name: /a\.py/i });
		expect(selected).toHaveAttribute("aria-current", "true");

		const unselected = screen.getByRole("button", { name: /Unknown file/i });
		expect(unselected).not.toHaveAttribute("aria-current", "true");
	});

	it("calls onSelect when a different file button is clicked", async () => {
		const user = userEvent.setup();
		const onSelect = vi.fn();
		render(
			<FileReviewNavigator
				groups={groups}
				selectedKey="a.py"
				onSelect={onSelect}
			/>,
		);

		await user.click(screen.getByRole("button", { name: /Unknown file/i }));
		expect(onSelect).toHaveBeenCalledWith("__unknown_file__");
	});
});
