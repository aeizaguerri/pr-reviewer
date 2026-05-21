import { useEffect, useRef, type ReactNode } from "react";

type MobileReviewDrawerProps = {
	open: boolean;
	onClose: () => void;
	onOpen: () => void;
	children: ReactNode;
};

export function MobileReviewDrawer({ open, onClose, onOpen, children }: MobileReviewDrawerProps) {
	const triggerRef = useRef<HTMLButtonElement>(null);
	const closeButtonRef = useRef<HTMLButtonElement>(null);

	useEffect(() => {
		if (open) {
			closeButtonRef.current?.focus();
		} else {
			triggerRef.current?.focus();
		}
	}, [open]);

	useEffect(() => {
		function handleKeyDown(event: KeyboardEvent) {
			if (event.key === "Escape" && open) {
				onClose();
			}
		}
		document.addEventListener("keydown", handleKeyDown);
		return () => document.removeEventListener("keydown", handleKeyDown);
	}, [open, onClose]);

	return (
		<>
			{!open ? (
				<button
					ref={triggerRef}
					className="hamburger-trigger"
					type="button"
					aria-label="Open review controls"
					onClick={onOpen}
				>
					☰ Review
				</button>
			) : null}

			{open ? (
				<>
					<div className="mobile-drawer-overlay" onClick={onClose} aria-hidden="true" />
					<div
						className="mobile-drawer"
						role="dialog"
						aria-modal="true"
						aria-label="Review controls"
					>
						<button
							ref={closeButtonRef}
							className="mobile-drawer-close"
							type="button"
							onClick={onClose}
						>
							Close
						</button>
						{children}
					</div>
				</>
			) : null}
		</>
	);
}
