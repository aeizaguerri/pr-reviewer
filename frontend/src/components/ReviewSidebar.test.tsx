import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewSidebar } from "./ReviewSidebar";

describe("ReviewSidebar", () => {
	it("renders expanded by default with aria-expanded true", () => {
		render(
			<ReviewSidebar expanded={true} onToggle={() => undefined}>
				<p>Controls</p>
			</ReviewSidebar>,
		);
		expect(
			screen.getByRole("button", { name: /collapse/i }),
		).toHaveAttribute("aria-expanded", "true");
	});

	it("renders collapsed with aria-expanded false", () => {
		render(
			<ReviewSidebar expanded={false} onToggle={() => undefined}>
				<p>Controls</p>
			</ReviewSidebar>,
		);
		expect(
			screen.getByRole("button", { name: /expand/i }),
		).toHaveAttribute("aria-expanded", "false");
	});

	it("keeps children mounted while collapsed so form state can survive", () => {
		render(
			<ReviewSidebar expanded={false} onToggle={() => undefined}>
				<input aria-label="GitHub token" defaultValue="gh-token" />
			</ReviewSidebar>,
		);

		expect(screen.getByLabelText(/github token/i)).toHaveValue("gh-token");
	});

	it("calls onToggle when toggle button is clicked", async () => {
		const user = userEvent.setup();
		const onToggle = vi.fn();
		render(
			<ReviewSidebar expanded={true} onToggle={onToggle}>
				<p>Controls</p>
			</ReviewSidebar>,
		);

		await user.click(screen.getByRole("button", { name: /collapse/i }));
		expect(onToggle).toHaveBeenCalledTimes(1);
	});

	it("renders children inside the sidebar", () => {
		render(
			<ReviewSidebar expanded={true} onToggle={() => undefined}>
				<p>Controls</p>
			</ReviewSidebar>,
		);
		expect(screen.getByText("Controls")).toBeInTheDocument();
	});
});
