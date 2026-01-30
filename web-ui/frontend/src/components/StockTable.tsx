import { Download } from 'lucide-react'

interface StockRow {
    rank: number
    code: string
    name: string
    change: number
    score: number
}

const mockData: StockRow[] = [
    { rank: 1, code: '600519', name: '贵州茅台', change: 5.23, score: 92 },
    { rank: 2, code: '000858', name: '五粮液', change: 4.87, score: 88 },
    { rank: 3, code: '601318', name: '中国平安', change: 3.56, score: 85 },
    { rank: 4, code: '600036', name: '招商银行', change: -1.24, score: 72 },
    { rank: 5, code: '600000', name: '浦发银行', change: 2.18, score: 78 },
]

function getScoreColor(score: number) {
    if (score >= 85) return 'bg-primary'
    if (score >= 75) return 'bg-success'
    return 'bg-warning'
}

export default function StockTable() {
    return (
        <div className="flex-1 border border-border flex flex-col min-h-0">
            {/* 头部 */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                <h2 className="font-primary text-lg font-semibold text-foreground">
                    竞价排行榜 - 今日热门
                </h2>
                <button className="h-8 px-3 border border-border flex items-center gap-1.5 hover:bg-surface transition-colors">
                    <Download size={14} className="text-muted-foreground" />
                    <span className="font-primary text-xs font-medium text-foreground">导出</span>
                </button>
            </div>

            {/* 表格 */}
            <div className="flex-1 flex flex-col min-h-0 overflow-auto">
                {/* 表头 */}
                <div className="flex bg-surface border-b border-border sticky top-0">
                    <div className="w-20 px-5 py-3.5">
                        <span className="font-secondary text-xs font-medium text-muted-foreground">排名</span>
                    </div>
                    <div className="flex-1 px-5 py-3.5">
                        <span className="font-secondary text-xs font-medium text-muted-foreground">股票代码</span>
                    </div>
                    <div className="flex-1 px-5 py-3.5">
                        <span className="font-secondary text-xs font-medium text-muted-foreground">股票名称</span>
                    </div>
                    <div className="w-[120px] px-5 py-3.5">
                        <span className="font-secondary text-xs font-medium text-muted-foreground">涨跌幅</span>
                    </div>
                    <div className="w-[120px] px-5 py-3.5">
                        <span className="font-secondary text-xs font-medium text-muted-foreground">评分</span>
                    </div>
                    <div className="w-[100px] px-5 py-3.5">
                        <span className="font-secondary text-xs font-medium text-muted-foreground">操作</span>
                    </div>
                </div>

                {/* 表体 */}
                <div className="flex-1">
                    {mockData.map((row) => (
                        <div key={row.code} className="flex border-b border-border hover:bg-surface/50 transition-colors">
                            <div className="w-20 px-5 py-4">
                                <span className="font-primary text-sm font-semibold text-foreground">{row.rank}</span>
                            </div>
                            <div className="flex-1 px-5 py-4">
                                <span className="font-primary text-sm font-medium text-foreground">{row.code}</span>
                            </div>
                            <div className="flex-1 px-5 py-4">
                                <span className="font-primary text-sm font-medium text-foreground">{row.name}</span>
                            </div>
                            <div className="w-[120px] px-5 py-4">
                                <span className={`font-primary text-sm font-semibold ${row.change >= 0 ? 'text-success' : 'text-error'}`}>
                                    {row.change >= 0 ? '+' : ''}{row.change.toFixed(2)}%
                                </span>
                            </div>
                            <div className="w-[120px] px-5 py-4 flex items-center">
                                <span className={`${getScoreColor(row.score)} px-3 py-1 font-secondary text-xs font-medium text-white`}>
                                    {row.score}分
                                </span>
                            </div>
                            <div className="w-[100px] px-5 py-4">
                                <button className="font-primary text-xs font-medium text-primary hover:underline">
                                    分析
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}
