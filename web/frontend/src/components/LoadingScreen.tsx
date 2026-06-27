interface LoadingScreenProps {
  message?: string;
  submessage?: string;
}

export function LoadingScreen({ message = "Loading…", submessage }: LoadingScreenProps) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-market-DEFAULT">
      <div className="text-center animate-fade-in">
        <div className="w-12 h-12 mx-auto mb-4 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
        <p className="text-sm text-slate-500 font-medium">{message}</p>
        {submessage && <p className="text-xs text-slate-600 mt-2">{submessage}</p>}
      </div>
    </div>
  );
}
