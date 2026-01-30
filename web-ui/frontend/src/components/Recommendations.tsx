import { ChevronRight } from 'lucide-react'

interface RecommendationItem {
    code: string
    name: string
    score: number
    reason: string
}

const mockRecommendations: RecommendationItem[] = [
    {
        code: '600519',
        name: '贵州茅台',
        score: 92,
        reason: '业绩稳健，估值合理'
    },
    {
        code: '300750',
        name: '宁德时代',
        score: 88,
        reason: '新能源龙头，技术领先'
    },
    {
        code: '002594',
        name: '比亚迪',
        score: 85,
        reason: '销量增长强劲'
    },
    {
        code: '601012',
        name: '隆基绿能',
        score: 82,
        reason: '光伏产业链完整'
    },
]

function getScoreBgColor(score: number) {
    if (score >= 90) return 'bg-primary'
    if (score >= 80) return 'bg-success'
    return 'bg-warning'
}

export default function Recommendations() {
    return (
        <div className="border border-border">
            {/* 头部 */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <h3 className="font-primary text-base font-semibold text-foreground">
                    AI 推荐
                </h3>
                <button className="flex items-center gap-1 text-primary hover:underline">
                    <span className="font-primary text-xs font-medium">查看全部</span>
                    <ChevronRight size={14} />
                </button>
            </div>

            {/* 列表 */}
            <div className="flex flex-col">
                {mockRecommendations.map((item, index) => (
                    <div
                        key={item.code}
                        className={`px-5 py-4 flex gap-3 ${index < mockRecommendations.length - 1 ? 'border-b border-border' : ''} hover:bg-surface transition-colors cursor-pointer`}
                    >
                        {/* 评分 */}
                        <div className={`w-10 h-10 ${getScoreBgColor(item.score)} flex items-center justify-center flex-shrink-0`}>
                            <span className="font-primary text-sm font-bold text-white">{item.score}</span>
                        </div>

                        {/* 内容 */}
                        <div className="flex-1 flex flex-col gap-1 min-w-0">
                            <div className="flex items-center gap-2">
                                <span className="font-primary text-sm font-semibold text-foreground">{item.name}</span>
                                <span className="font-secondary text-xs text-muted-foreground">{item.code}</span>
                            </div>
                            <span className="font-secondary text-xs text-muted-foreground truncate">
                                {item.reason}
                            </span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}
