import { ChevronDown, Layers, Search } from 'lucide-react'
import { useState } from 'react'

export default function StockAnalysis() {
    const [stockCode, setStockCode] = useState('')
    const [llmModel, setLlmModel] = useState('DeepSeek')
    const [period, setPeriod] = useState('短期分析')

    const handleAnalyze = () => {
        console.log('分析股票:', stockCode, llmModel, period)
        // TODO: 调用 API
    }

    return (
        <div className="border border-border">
            {/* 头部 */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-border">
                <h2 className="font-primary text-lg font-semibold text-foreground">
                    股票分析
                </h2>
            </div>

            {/* 内容 */}
            <div className="p-6 flex flex-col gap-5">
                {/* 输入行 */}
                <div className="flex gap-4">
                    <div className="flex-1 h-11 border border-border flex items-center px-4">
                        <input
                            type="text"
                            value={stockCode}
                            onChange={(e) => setStockCode(e.target.value)}
                            placeholder="输入股票代码 (如: 600519)"
                            className="flex-1 font-secondary text-sm text-foreground placeholder:text-muted-foreground outline-none bg-transparent"
                        />
                    </div>
                    <button
                        onClick={handleAnalyze}
                        className="h-11 px-6 bg-primary flex items-center gap-2 hover:opacity-90 transition-opacity"
                    >
                        <Search size={14} className="text-white" />
                        <span className="font-primary text-sm font-medium text-white">查询</span>
                    </button>
                </div>

                {/* 控制行 */}
                <div className="flex gap-3">
                    {/* LLM 选择 */}
                    <button className="h-9 px-4 border border-border flex items-center gap-2 hover:bg-surface transition-colors">
                        <span className="font-primary text-xs font-medium text-foreground">
                            LLM: {llmModel}
                        </span>
                        <ChevronDown size={14} className="text-muted-foreground" />
                    </button>

                    {/* 周期选择 */}
                    <button className="h-9 px-4 border border-border flex items-center gap-2 hover:bg-surface transition-colors">
                        <span className="font-primary text-xs font-medium text-foreground">
                            {period}
                        </span>
                        <ChevronDown size={14} className="text-muted-foreground" />
                    </button>

                    {/* 批量分析 */}
                    <button className="h-9 px-4 bg-foreground flex items-center gap-2 hover:opacity-90 transition-opacity">
                        <Layers size={14} className="text-white" />
                        <span className="font-primary text-xs font-medium text-white">
                            批量分析
                        </span>
                    </button>
                </div>
            </div>
        </div>
    )
}
