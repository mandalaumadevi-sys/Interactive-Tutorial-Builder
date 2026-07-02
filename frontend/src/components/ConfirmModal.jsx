// A small confirmation dialog. Used to stop an accidental "Accept" when the reviewer has typed
// feedback that hasn't been applied — so a wasted regeneration / lost feedback can be averted.
export default function ConfirmModal({
  open, title, message,
  confirmLabel = "Discard & accept anyway", cancelLabel = "Go back",
  onConfirm, onCancel,
}) {
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onCancel} role="presentation">
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h3 className="modal-title">{title}</h3>
        <p className="modal-msg">{message}</p>
        <div className="modal-actions">
          <button className="green" onClick={onCancel}>{cancelLabel}</button>
          <button className="ghost danger" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
