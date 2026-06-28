import { BarChart3 } from "lucide-react";

export function LoginPage() {
  const handleLogin = async () => {
    try {
      const res = await fetch('/api/auth/login');
      const data = await res.json();
      if (data.auth_url) {
        window.location.href = data.auth_url;
      }
    } catch {
      window.location.href = '/api/auth/login';
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-market-DEFAULT relative overflow-hidden">
      <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
        <div className="absolute -top-40 -left-40 w-[600px] h-[600px] rounded-full bg-sky-500/5 blur-[150px] animate-breathing" />
        <div className="absolute -bottom-40 -right-40 w-[700px] h-[700px] rounded-full bg-emerald-500/5 blur-[180px]" />
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[500px] h-[300px] bg-violet-500/3 blur-[120px]" />
      </div>
      <div className="relative text-center animate-fade-in">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-sky-500/15 to-emerald-500/15 border border-sky-500/20 mb-6 mx-auto shadow-[0_0_20px_rgba(56,189,248,0.1)]">
          <BarChart3 className="w-8 h-8 text-sky-400" />
        </div>
        <h1 className="text-3xl font-display font-semibold text-slate-100 tracking-tight mb-2">
          TradingAgents
        </h1>
        <p className="text-sm text-slate-500 mb-8">Multi-Agent LLM Trading Dashboard</p>
        <button
          onClick={handleLogin}
          className="inline-flex items-center gap-3 px-6 py-3 bg-white text-gray-900 rounded-xl hover:bg-gray-100 transition-all font-medium shadow-lg hover:shadow-xl active:scale-[0.98]"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Sign in with Google
        </button>
      </div>
    </div>
  );
}
