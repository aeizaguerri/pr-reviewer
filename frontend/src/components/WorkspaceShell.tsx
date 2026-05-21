import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { ReviewResponse } from "../api/types";
import { buildReviewDisplay, buildReviewWorkspaceDisplay } from "../lib/displayModel";
import { FileReviewDetail } from "./FileReviewDetail";
import { FileReviewNavigator } from "./FileReviewNavigator";
import { MobileReviewDrawer } from "./MobileReviewDrawer";
import { ReviewSidebar } from "./ReviewSidebar";

type WorkspaceShellProps = {
	latestReview: ReviewResponse | null;
	sidebar?: ReactNode;
};

function useIsMobile() {
	const [isMobile, setIsMobile] = useState(() => {
		if (typeof window === "undefined" || !window.matchMedia) return false;
		return window.matchMedia("(max-width: 767px)").matches;
	});

	useEffect(() => {
		if (typeof window === "undefined" || !window.matchMedia) return;
		const mql = window.matchMedia("(max-width: 767px)");
		const handler = (event: MediaQueryListEvent) => setIsMobile(event.matches);
		mql.addEventListener("change", handler);
		return () => mql.removeEventListener("change", handler);
	}, []);

	return isMobile;
}

export function WorkspaceShell({ latestReview, sidebar }: WorkspaceShellProps) {
	const isMobile = useIsMobile();
	const [sidebarExpanded, setSidebarExpanded] = useState(true);
	const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
	const [selectedFileKey, setSelectedFileKey] = useState<string | null>(null);

	const display = useMemo(
		() => buildReviewWorkspaceDisplay(latestReview ?? {}),
		[latestReview],
	);

	useEffect(() => {
		if (selectedFileKey == null && display.selectedFileKey != null) {
			setSelectedFileKey(display.selectedFileKey);
		}
	}, [display.selectedFileKey, selectedFileKey]);

	const selectedGroup = display.groups.find((g) => g.key === selectedFileKey);
	const reviewHeader = useMemo(() => {
		if (!latestReview) return null;
		return buildReviewDisplay(latestReview);
	}, [latestReview]);

	const hasFindings = display.groups.length > 0;

	return (
		<div
			className={`workspace-shell ${!isMobile && !sidebarExpanded ? "sidebar-collapsed" : ""}`}
		>
			<header className="workspace-topbar">
				<div>
					<p className="workspace-kicker">PR Reviewer</p>
					<h1>Review workspace</h1>
				</div>
				<p className="workspace-topbar-meta">
					Inspect affected files, code context, and agent findings in one editor-style surface.
				</p>
			</header>
			{isMobile ? (
				<MobileReviewDrawer
					open={mobileDrawerOpen}
					onClose={() => setMobileDrawerOpen(false)}
					onOpen={() => setMobileDrawerOpen(true)}
				>
					{sidebar}
				</MobileReviewDrawer>
			) : (
				<ReviewSidebar
					expanded={sidebarExpanded}
					onToggle={() => setSidebarExpanded((v) => !v)}
				>
					{sidebar}
				</ReviewSidebar>
			)}
			<main className="workspace-main" aria-label="Review workspace">
				{hasFindings ? (
					<FileReviewNavigator
						groups={display.groups}
						selectedKey={selectedFileKey ?? ""}
						onSelect={(key) => setSelectedFileKey(key)}
					/>
				) : (
					<nav className="file-navigator file-navigator-empty" aria-label="File findings">
						<p className="pane-label">Affected files</p>
						<div className="empty-file-row" aria-current="true">
							<span className="file-navigator-label">No file selected</span>
							<span className="file-navigator-meta">Run a review to populate this pane</span>
						</div>
					</nav>
				)}
				{reviewHeader ? (
					<>
						<section className="review-summary-pane" aria-label="Review summary">
							<div className="result-header">
								<div
									className="approval-badge"
									data-approved={reviewHeader.approved}
								>
									<strong>{reviewHeader.approvalLabel}</strong>
									<span>{reviewHeader.approvalDelta}</span>
								</div>
							</div>
							{reviewHeader.summary ? <p>{reviewHeader.summary}</p> : null}
						</section>
						{display.groups.length === 0 ? (
							<section className="file-detail">
								<p className="file-detail-empty">
									No findings — this review came back clean.
								</p>
							</section>
						) : (
							<>
								{selectedGroup ? (
									<FileReviewDetail group={selectedGroup} />
								) : (
									<section className="file-detail">
										<p className="file-detail-empty">
											Select a file to view findings.
										</p>
									</section>
								)}
							</>
						)}
					</>
				) : (
					<section className="file-detail file-detail-empty-state" aria-label="Empty review workspace">
						<p className="pane-label">Code review pane</p>
						<h2>No review data yet</h2>
						<p>
							Submit a PR review from the controls panel to inspect affected files,
							line-level findings, and code context here.
						</p>
						<div className="code-context-block placeholder" aria-hidden="true">
							<span>diff --review pending</span>{"\n"}
							<span>@@ select a repository and pull request @@</span>{"\n"}
							<span>+ findings will appear grouped by file</span>
						</div>
					</section>
				)}
			</main>
		</div>
	);
}
