import { AlertCircle, CheckCircle2, Cpu, Database } from 'lucide-react'

interface StatusItem {
    name: string
    status: 'online' | 'offline' | 'warning'
    icon: 'database' | 'cpu'
}

const statusItems: StatusItem[] = [
    { name: '数据源连接', status: 'online', icon: 'database' },
    { name: 'K线数据', status: 'online', icon: 'database' },
    { name: 'Choice API', status: 'online', icon: 'database' },
    { name: 'AI 模型', status: 'online', icon: 'cpu' },
]

function getStatusBadge(status: StatusItem['status']) {
    switch (status) {
        case 'online':
            return (
                <div className="flex items-center gap-1.5">
                    <CheckCircle2 size={12} className="text-success" />
                    <span className="font-secondary text-xs text-success">在线</span>
                </div>
            )
        case 'offline':
            return (
                <div className="flex items-center gap-1.5">
                    <AlertCircle size={12} className="text-error" />
                    <span className="font-secondary text-xs text-error">离线</span>
                </div>
            )
        case 'warning':
            return (
                <div className="flex items-center gap-1.5">
                    <AlertCircle size={12} className="text-warning" />
                    <span className="font-secondary text-xs text-warning">警告</span>
                </div>
            )
    }
}

function getIcon(type: StatusItem['icon']) {
    switch (type) {
        case 'database':
            return <Database size={16} className="text-muted-foreground" />
        case 'cpu':
            return <Cpu size={16} className="text-muted-foreground" />
    }
}

export default function SystemStatus() {
    return (
        <div className="border border-border">
            {/* 头部 */}
            <div className="px-5 py-4 border-b border-border">
                <h3 className="font-primary text-base font-semibold text-foreground">
                    系统状态
                </h3>
            </div>

            {/* 状态列表 */}
            <div className="flex flex-col">
                {statusItems.map((item, index) => (
                    <div
                        key={item.name}
                        className={`px-5 py-3.5 flex items-center justify-between ${index < statusItems.length - 1 ? 'border-b border-border' : ''}`}
                    >
                        <div className="flex items-center gap-3">
                            {getIcon(item.icon)}
                            <span className="font-primary text-sm text-foreground">{item.name}</span>
                        </div>
                        {getStatusBadge(item.status)}
                    </div>
                ))}
            </div>

            {/* 最后更新时间 */}
            <div className="px-5 py-3 bg-surface border-t border-border">
                <span className="font-secondary text-xs text-muted-foreground">
                    最后更新: {new Date().toLocaleString('zh-CN')}
                </span>
            </div>
        </div>
    )
}
