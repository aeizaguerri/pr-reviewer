import type { ReactNode } from "react";

type ReviewSidebarProps = {
	expanded: boolean;
	onToggle: () => void;
	children: ReactNode;
};

export function ReviewSidebar({ expanded, onToggle, children }: ReviewSidebarProps) {
	return (
		<aside
			className={`review-sidebar ${expanded ? "" : "collapsed"}`}
			aria-label="Review controls"
		>
			<button
				className="sidebar-toggle"
				type="button"
				aria-expanded={expanded}
				onClick={onToggle}
			>
				{expanded ? "Collapse sidebar" : "Expand sidebar"}
			</button>
			<div className="sidebar-content" aria-hidden={!expanded}>
				{children}
			</div>
		</aside>
	);
}
