interface LoadingScreenProps {
  message?: string;
  submessage?: string;
}

export function LoadingScreen({ message = "Loading…", submessage }: LoadingScreenProps) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-market-DEFAULT">
      <div className="text-center animate-fade-in">
        <div className="relative w-12 h-12 mx-auto mb-4">
          <div className="absolute inset-0 rounded-full bg-sky-500/10 blur-md animate-pulse" />
          <div className="w-12 h-12 rounded-full border-2 border-sky-500/20 border-t-sky-400 animate-spin" />
        </div>
        <p className="text-sm text-slate-400 font-medium">{message}</p>
        {submessage && <p className="text-xs text-slate-600 mt-1.5">{submessage}</p>}
      </div>
    </div>
  );
}
