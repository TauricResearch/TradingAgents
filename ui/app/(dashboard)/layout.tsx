import Sidebar from '@/components/Sidebar'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)', color: 'var(--text-high)' }}>
      <Sidebar />
      <main className="flex-1 overflow-auto relative">
        {/* Subtle mesh background */}
        <div
          className="fixed inset-0 pointer-events-none"
          style={{
            background: `
              radial-gradient(ellipse 50% 40% at 70% 15%, rgba(0,196,232,0.04) 0%, transparent 60%),
              radial-gradient(ellipse 40% 50% at 20% 80%, rgba(80,40,200,0.04) 0%, transparent 60%)
            `,
            zIndex: 0,
          }}
        />
        <div className="relative z-10 p-8">
          {children}
        </div>
      </main>
    </div>
  )
}
