import { type FormEvent, useMemo, useState } from "react";
import type { ProviderInfo, ReviewResponse } from "../api/types";
import { type ReviewFormInput, validateReviewForm } from "../lib/validation";
import { useReviewSubmission } from "../hooks/useReviewSubmission";

type ReviewFormProps = {
	providers: ProviderInfo[];
	onReviewComplete: (review: ReviewResponse) => void;
};

const emptyInput: ReviewFormInput = {
	repoSlug: "",
	prNumber: "",
	provider: "",
	providerApiKey: "",
	githubToken: "",
	model: "",
	baseUrlOverride: "",
};

export function ReviewForm({ providers, onReviewComplete }: ReviewFormProps) {
	const [input, setInput] = useState<ReviewFormInput>(emptyInput);
	const { state, runReview } = useReviewSubmission(onReviewComplete);

	const selectedProvider = providers.find(
		(provider) => provider.key === input.provider,
	);
	const validation = useMemo(() => validateReviewForm(input), [input]);
	const errors = validation.valid ? {} : validation.errors;
	const isLoading = state.status === "loading";
	const canSubmit = validation.valid && !isLoading;

	function updateField(field: keyof ReviewFormInput, value: string) {
		setInput((current) => ({ ...current, [field]: value }));
	}

	function submit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		const result = validateReviewForm(input);
		if (!result.valid || isLoading) {
			return;
		}
		void runReview(result.value);
	}

	return (
		<form
			className="review-form"
			aria-label="Review form"
			onSubmit={submit}
			noValidate
		>
			<div className="field-group">
				<label htmlFor="provider">Provider</label>
				<select
					id="provider"
					value={input.provider}
					onChange={(event) => updateField("provider", event.target.value)}
					aria-invalid={Boolean(errors.provider)}
				>
					<option value="">Choose a provider</option>
					{providers.map((provider) => (
						<option key={provider.key} value={provider.key}>
							{provider.key} — {provider.description}
						</option>
					))}
				</select>
				{selectedProvider ? (
					<p className="field-hint">
						Default model: {selectedProvider.default_model}
					</p>
				) : null}
				{errors.provider ? (
					<p className="field-error">{errors.provider}</p>
				) : null}
			</div>

			<div className="field-grid">
				<div className="field-group">
					<label htmlFor="repoSlug">Repository</label>
					<input
						id="repoSlug"
						placeholder="owner/repo"
						value={input.repoSlug}
						onChange={(event) => updateField("repoSlug", event.target.value)}
						aria-invalid={Boolean(errors.repoSlug)}
					/>
					{errors.repoSlug ? (
						<p className="field-error">{errors.repoSlug}</p>
					) : null}
				</div>

				<div className="field-group">
					<label htmlFor="prNumber">Pull request number</label>
					<input
						id="prNumber"
						inputMode="numeric"
						value={input.prNumber}
						onChange={(event) => updateField("prNumber", event.target.value)}
						aria-invalid={Boolean(errors.prNumber)}
					/>
					{errors.prNumber ? (
						<p className="field-error">{errors.prNumber}</p>
					) : null}
				</div>
			</div>

			<div className="field-grid">
				<div className="field-group">
					<label htmlFor="model">Model override</label>
					<input
						id="model"
						value={input.model}
						onChange={(event) => updateField("model", event.target.value)}
					/>
				</div>

				<div className="field-group">
					<label htmlFor="baseUrlOverride">Base URL override</label>
					<input
						id="baseUrlOverride"
						value={input.baseUrlOverride}
						onChange={(event) =>
							updateField("baseUrlOverride", event.target.value)
						}
					/>
				</div>
			</div>

			<div className="field-grid">
				<div className="field-group">
					<label htmlFor="providerApiKey">Provider API key</label>
					<input
						id="providerApiKey"
						type="password"
						value={input.providerApiKey}
						onChange={(event) =>
							updateField("providerApiKey", event.target.value)
						}
						aria-invalid={Boolean(errors.providerApiKey)}
					/>
					{errors.providerApiKey ? (
						<p className="field-error">{errors.providerApiKey}</p>
					) : null}
				</div>

				<div className="field-group">
					<label htmlFor="githubToken">GitHub token</label>
					<input
						id="githubToken"
						type="password"
						value={input.githubToken}
						onChange={(event) => updateField("githubToken", event.target.value)}
						aria-invalid={Boolean(errors.githubToken)}
					/>
					{errors.githubToken ? (
						<p className="field-error">{errors.githubToken}</p>
					) : null}
				</div>
			</div>

			<p className="secret-note">
				Secrets are kept only in this page state and sent to the backend for
				this review request.
			</p>

			{state.status === "loading" ? (
				<p role="status">Reviews can take several minutes.</p>
			) : null}
			{state.status === "error" ? <p role="alert">{state.message}</p> : null}
			{state.status === "success" ? (
				<p role="status">
					Review completed. Result details arrive in the next UI slice.
				</p>
			) : null}

			<button type="submit" disabled={!canSubmit}>
				{isLoading ? "Running review" : "Run review"}
			</button>
		</form>
	);
}
