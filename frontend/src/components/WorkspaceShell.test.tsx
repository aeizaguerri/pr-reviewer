import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkspaceShell } from "./WorkspaceShell";
import type { ReviewResponse } from "../api/types";

function mockMatchMedia(matches: boolean) {
	Object.defineProperty(window, "matchMedia", {
		writable: true,
		value: vi.fn().mockImplementation((query: string) => ({
			matches,
			media: query,
			onchange: null,
			addEventListener: vi.fn(),
			removeEventListener: vi.fn(),
			dispatchEvent: vi.fn(),
		})),
	});
}

const sampleReview: ReviewResponse = {
	summary: "Found issues",
	approved: false,
	bugs: [
		{ file: "b.py", line: 1, severity: "major", description: "d1", suggestion: "s1", category: "bug", source: "" },
		{ file: "a.py", line: 2, severity: "critical", description: "d2", suggestion: "s2", category: "bug", source: "" },
	],
	impact_warnings: [],
	review_health: null,
};

describe("WorkspaceShell", () => {
	beforeEach(() => {
		mockMatchMedia(false);
	});

	it("renders desktop sidebar by default on desktop", () => {
		mockMatchMedia(false);
		render(<WorkspaceShell latestReview={sampleReview} />);
		expect(
			screen.getByRole("button", { name: /collapse/i }),
		).toBeInTheDocument();
	});

	it("keeps an expand control available after the desktop sidebar collapses", async () => {
		mockMatchMedia(false);
		render(<WorkspaceShell latestReview={sampleReview} />);
		const user = userEvent.setup();

		await user.click(screen.getByRole("button", { name: /collapse sidebar/i }));

		expect(
			screen.getByRole("button", { name: /expand sidebar/i }),
		).toHaveAttribute("aria-expanded", "false");
	});

	it("preserves sidebar form state across desktop collapse and expand", async () => {
		mockMatchMedia(false);
		render(
			<WorkspaceShell
				latestReview={null}
				sidebar={<input aria-label="GitHub token" defaultValue="" />}
			/>,
		);
		const user = userEvent.setup();
		const tokenInput = screen.getByLabelText(/github token/i);

		await user.type(tokenInput, "ghp_secret");
		await user.click(screen.getByRole("button", { name: /collapse sidebar/i }));
		await user.click(screen.getByRole("button", { name: /expand sidebar/i }));

		expect(screen.getByLabelText(/github token/i)).toHaveValue("ghp_secret");
	});

	it("renders mobile hamburger trigger on mobile", () => {
		mockMatchMedia(true);
		render(<WorkspaceShell latestReview={sampleReview} />);
		expect(
			screen.getByRole("button", { name: /open review controls/i }),
		).toBeInTheDocument();
	});

	it("opens mobile drawer when hamburger trigger is clicked", async () => {
		mockMatchMedia(true);
		render(<WorkspaceShell latestReview={sampleReview} />);
		const user = userEvent.setup();
		await user.click(screen.getByRole("button", { name: /open review controls/i }));
		expect(screen.getByRole("dialog")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /close/i })).toBeInTheDocument();
	});

	it("shows file navigator and detail for the review", () => {
		mockMatchMedia(false);
		render(<WorkspaceShell latestReview={sampleReview} />);
		expect(screen.getByRole("navigation", { name: /file findings/i })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: /a\.py/i })).toBeInTheDocument();
	});

	it("updates detail pane when a different file is selected", async () => {
		mockMatchMedia(false);
		render(<WorkspaceShell latestReview={sampleReview} />);

		expect(screen.getByRole("heading", { name: /a\.py/i })).toBeInTheDocument();

		const user = userEvent.setup();
		await user.click(screen.getByRole("button", { name: /b\.py/i }));

		expect(screen.getByRole("heading", { name: /b\.py/i })).toBeInTheDocument();
	});

	it("shows clean state when review is null", () => {
		mockMatchMedia(false);
		render(<WorkspaceShell latestReview={null} />);
		expect(screen.getByText(/no review data/i)).toBeInTheDocument();
		expect(
			screen.getByRole("button", { name: /collapse sidebar/i }),
		).toBeInTheDocument();
	});

	it("renders sidebar content when provided", () => {
		mockMatchMedia(false);
		render(
			<WorkspaceShell
				latestReview={null}
				sidebar={<div data-testid="sidebar-content">Controls</div>}
			/>,
		);
		expect(screen.getByTestId("sidebar-content")).toBeInTheDocument();
	});

	it("shows clean state when review has no findings", () => {
		mockMatchMedia(false);
		render(
			<WorkspaceShell
				latestReview={{
					summary: "Clean",
					approved: true,
					bugs: [],
					impact_warnings: [],
					review_health: null,
				}}
			/>,
		);
		expect(screen.getByText(/no findings/i)).toBeInTheDocument();
	});
});
