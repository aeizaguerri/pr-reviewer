import type { FileFindingGroup } from "../lib/displayModel";

type FileReviewNavigatorProps = {
	groups: FileFindingGroup[];
	selectedKey: string;
	onSelect: (key: string) => void;
};

export function FileReviewNavigator({
	groups,
	selectedKey,
	onSelect,
}: FileReviewNavigatorProps) {
	return (
		<nav className="file-navigator" aria-label="File findings">
			<ul className="file-navigator-list">
				{groups.map((group) => (
					<li key={group.key} className="file-navigator-item">
						<button
							className="file-navigator-button"
							aria-current={group.key === selectedKey ? "true" : undefined}
							onClick={() => onSelect(group.key)}
						>
							<span className="file-navigator-label">{group.fileLabel}</span>
							<span className="file-navigator-meta">
								{group.findings.length} finding
								{group.findings.length === 1 ? "" : "s"}
							</span>
						</button>
					</li>
				))}
			</ul>
		</nav>
	);
}
