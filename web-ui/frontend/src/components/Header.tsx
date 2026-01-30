import { Bell, RefreshCw, Search, TrendingUp } from 'lucide-react'

export default function Header() {
    return (
        <header className="flex flex-col gap-6 mb-8">
            {/* 顶部栏 */}
            <div className="flex items-center justify-between">
                <span className="font-secondary text-xs text-muted-foreground">
                    系统 / 概览
                </span>
                <div className="flex items-center gap-4">
                    <button className="p-1 hover:opacity-70 transition-opacity">
                        <Search size={18} className="text-muted-foreground" />
                    </button>
                    <button className="p-1 hover:opacity-70 transition-opacity">
                        <Bell size={18} className="text-muted-foreground" />
                    </button>
                </div>
            </div>

            {/* 标题区 */}
            <div className="flex items-center justify-between">
                <div className="flex flex-col gap-2">
                    <h1 className="font-primary text-4xl font-semibold text-foreground">
                        A股交易分析系统
                    </h1>
                    <p className="font-secondary text-sm text-muted-foreground">
                        实时监控主板股票，AI 智能分析投资机会
                    </p>
                </div>

                <div className="flex items-center gap-3">
                    <button className="flex items-center gap-2 px-5 py-2.5 border border-border hover:bg-surface transition-colors">
                        <RefreshCw size={14} className="text-muted-foreground" />
                        <span className="font-primary text-sm font-medium text-foreground">
                            刷新数据
                        </span>
                    </button>
                    <button className="flex items-center gap-2 px-5 py-2.5 bg-foreground hover:opacity-90 transition-opacity">
                        <TrendingUp size={14} className="text-white" />
                        <span className="font-primary text-sm font-medium text-white">
                            开始分析
                        </span>
                    </button>
                </div>
            </div>
        </header>
    )
}
