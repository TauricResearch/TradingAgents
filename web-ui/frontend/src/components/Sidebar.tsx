import {
    BarChart3,
    LayoutDashboard,
    PieChart,
    Settings,
    Sparkles,
    TrendingUp,
    Zap
} from 'lucide-react'

interface SidebarProps {
    activeNav: string
    onNavChange: (nav: string) => void
}

const navItems = [
    { id: '概览', label: '系统概览', icon: LayoutDashboard },
    { id: '竞价', label: '竞价排行', icon: TrendingUp },
    { id: '分析', label: '股票分析', icon: BarChart3 },
    { id: '筹码', label: '筹码健康', icon: PieChart },
    { id: '推荐', label: '智能推荐', icon: Sparkles },
    { id: '设置', label: '系统设置', icon: Settings },
]

export default function Sidebar({ activeNav, onNavChange }: SidebarProps) {
    return (
        <aside className="w-[240px] h-full flex flex-col justify-between border-r border-border bg-background px-8 py-10">
            {/* 顶部 */}
            <div className="flex flex-col gap-12">
                {/* Logo */}
                <div className="flex items-center gap-3">
                    <div className="w-7 h-7 bg-primary" />
                    <span className="font-primary text-lg font-semibold text-foreground">
                        TradingAgents
                    </span>
                </div>

                {/* 导航 */}
                <nav className="flex flex-col gap-2">
                    {navItems.map((item) => {
                        const isActive = activeNav === item.id
                        const Icon = item.icon
                        return (
                            <button
                                key={item.id}
                                onClick={() => onNavChange(item.id)}
                                className="flex items-center gap-3 py-3 px-0 text-left transition-colors"
                            >
                                <div
                                    className={`w-1.5 h-1.5 ${isActive ? 'bg-primary' : 'bg-transparent'}`}
                                />
                                <Icon
                                    size={16}
                                    className={isActive ? 'text-foreground' : 'text-muted-foreground'}
                                />
                                <span
                                    className={`font-primary text-sm ${isActive
                                            ? 'text-foreground font-medium'
                                            : 'text-muted-foreground'
                                        }`}
                                >
                                    {item.label}
                                </span>
                            </button>
                        )
                    })}
                </nav>
            </div>

            {/* 底部 */}
            <div className="flex flex-col gap-6">
                {/* 升级卡片 */}
                <div className="border border-border bg-surface p-5 flex flex-col gap-3">
                    <span className="font-primary text-sm font-semibold text-foreground">
                        AI 分析助手
                    </span>
                    <p className="font-secondary text-xs text-muted-foreground">
                        启用 AI 智能分析
                        <br />
                        获取更精准的投资建议
                    </p>
                    <button className="w-full h-9 bg-primary flex items-center justify-center gap-2 transition-opacity hover:opacity-90">
                        <Zap size={14} className="text-white" />
                        <span className="font-primary text-xs font-medium text-white">
                            启用 AI
                        </span>
                    </button>
                </div>

                {/* 用户信息 */}
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 bg-foreground flex items-center justify-center">
                        <span className="font-primary text-xs font-medium text-white">A</span>
                    </div>
                    <div className="flex flex-col gap-0.5">
                        <span className="font-primary text-sm font-medium text-foreground">
                            Admin
                        </span>
                        <span className="font-secondary text-xs text-muted-foreground">
                            系统管理员
                        </span>
                    </div>
                </div>
            </div>
        </aside>
    )
}
