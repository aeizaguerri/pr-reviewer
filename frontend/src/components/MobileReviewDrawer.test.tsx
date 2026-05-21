import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MobileReviewDrawer } from "./MobileReviewDrawer";

describe("MobileReviewDrawer", () => {
	it("renders hamburger trigger when closed", () => {
		render(
			<MobileReviewDrawer open={false} onClose={() => undefined} onOpen={() => undefined}>
				<p>Controls</p>
			</MobileReviewDrawer>,
		);
		expect(
			screen.getByRole("button", { name: /open review controls/i }),
		).toBeInTheDocument();
	});

	it("calls onOpen when trigger is clicked", async () => {
		const user = userEvent.setup();
		const onOpen = vi.fn();
		render(
			<MobileReviewDrawer open={false} onClose={() => undefined} onOpen={onOpen}>
				<p>Controls</p>
			</MobileReviewDrawer>,
		);
		await user.click(screen.getByRole("button", { name: /open review controls/i }));
		expect(onOpen).toHaveBeenCalledTimes(1);
	});

	it("renders dialog with role and aria-modal when open", () => {
		render(
			<MobileReviewDrawer open={true} onClose={() => undefined} onOpen={() => undefined}>
				<p>Controls</p>
			</MobileReviewDrawer>,
		);
		const dialog = screen.getByRole("dialog");
		expect(dialog).toHaveAttribute("aria-modal", "true");
		expect(dialog).toHaveAccessibleName(/review controls/i);
	});

	it("calls onClose when close button is clicked", async () => {
		const user = userEvent.setup();
		const onClose = vi.fn();
		render(
			<MobileReviewDrawer open={true} onClose={onClose} onOpen={() => undefined}>
				<p>Controls</p>
			</MobileReviewDrawer>,
		);

		await user.click(screen.getByRole("button", { name: /close/i }));
		expect(onClose).toHaveBeenCalledTimes(1);
	});
});
