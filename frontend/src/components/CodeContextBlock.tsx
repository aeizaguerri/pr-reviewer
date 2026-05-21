type CodeContextBlockProps = {
	snippet?: string;
	language?: string;
};

export function CodeContextBlock({ snippet, language }: CodeContextBlockProps) {
	const hasSnippet = snippet != null && snippet.trim() !== "";

	if (!hasSnippet) {
		return (
			<pre className="code-context-block placeholder">
				No code snippet available
			</pre>
		);
	}

	return (
		<pre className="code-context-block" data-language={language}>
			{snippet}
		</pre>
	);
}
