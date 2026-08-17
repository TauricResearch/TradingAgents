export function StateBlock({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-xl border border-line bg-ink-800 p-6 text-center">
      <p className="text-sm font-medium text-white">{title}</p>
      <p className="mt-2 text-sm text-mist">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-md border border-gold/40 bg-gold/10 px-3 py-1.5 text-sm text-gold"
        >
          Retry
        </button>
      )}
    </div>
  );
}
