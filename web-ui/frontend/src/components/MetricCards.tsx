import { ArrowDown, ArrowUp, TrendingUp, Zap } from 'lucide-react'

interface MetricCardProps {
    label: string
    value: string
    change: string
    changeType: 'up' | 'down' | 'neutral'
    valueColor?: 'default' | 'success' | 'error' | 'primary'
    icon: React.ReactNode
}

function MetricCard({ label, value, change, changeType, valueColor = 'default', icon }: MetricCardProps) {
    const valueColorClass = {
        default: 'text-foreground',
        success: 'text-success',
        error: 'text-error',
        primary: 'text-primary',
    }[valueColor]

    const changeColorClass = changeType === 'up' ? 'text-success' : changeType === 'down' ? 'text-error' : 'text-muted-foreground'

    return (
        <div className="flex-1 border border-border p-7 flex flex-col gap-4">
            <span className="font-secondary text-xs text-muted-foreground">{label}</span>
            <span className={`font-primary text-3xl font-semibold ${valueColorClass}`}>
                {value}
            </span>
            <div className="flex items-center gap-2">
                {icon}
                <span className="font-secondary text-xs text-muted-foreground">{change}</span>
            </div>
        </div>
    )
}

export default function MetricCards() {
    return (
        <div className="flex gap-6">
            <MetricCard
                label="主板股票总数"
                value="4,396"
                change="+12 今日新增"
                changeType="up"
                icon={<TrendingUp size={14} className="text-success" />}
            />
            <MetricCard
                label="上涨股票"
                value="2,847"
                change="64.7% 上涨比例"
                changeType="up"
                valueColor="success"
                icon={<ArrowUp size={14} className="text-success" />}
            />
            <MetricCard
                label="下跌股票"
                value="1,243"
                change="28.3% 下跌比例"
                changeType="down"
                valueColor="error"
                icon={<ArrowDown size={14} className="text-error" />}
            />
            <MetricCard
                label="AI 智能推荐"
                value="86"
                change="高分推荐股票"
                changeType="neutral"
                valueColor="primary"
                icon={<Zap size={14} className="text-primary" />}
            />
        </div>
    )
}
