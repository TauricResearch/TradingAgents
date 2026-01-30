import { useState } from 'react'
import Header from './components/Header'
import MetricCards from './components/MetricCards'
import Recommendations from './components/Recommendations'
import Sidebar from './components/Sidebar'
import StockAnalysis from './components/StockAnalysis'
import StockTable from './components/StockTable'
import SystemStatus from './components/SystemStatus'

function App() {
    const [activeNav, setActiveNav] = useState('概览')

    return (
        <div className="flex h-full w-full bg-background">
            {/* 侧边栏 */}
            <Sidebar activeNav={activeNav} onNavChange={setActiveNav} />

            {/* 主内容区 */}
            <main className="flex-1 flex flex-col h-full overflow-hidden">
                <div className="flex-1 overflow-auto px-12 py-10">
                    {/* 页面头部 */}
                    <Header />

                    {/* 指标卡片 */}
                    <MetricCards />

                    {/* 内容区域 */}
                    <div className="flex gap-6 mt-8">
                        {/* 左侧列 */}
                        <div className="flex-1 flex flex-col gap-6">
                            {/* 股票分析卡片 */}
                            <StockAnalysis />

                            {/* 竞价排行表格 */}
                            <StockTable />
                        </div>

                        {/* 右侧列 */}
                        <div className="w-[360px] flex flex-col gap-6">
                            {/* 智能推荐 */}
                            <Recommendations />

                            {/* 系统状态 */}
                            <SystemStatus />
                        </div>
                    </div>
                </div>
            </main>
        </div>
    )
}

export default App
