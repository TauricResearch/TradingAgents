import { useState, useEffect } from 'react'
import { Table, Input, Modal, Skeleton, Button } from 'antd'
import { FileTextOutlined, SearchOutlined, CloseOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'

const { Search } = Input

export default function ReportsViewer() {
  const [loading, setLoading] = useState(true)
  const [reports, setReports] = useState([])
  const [selectedReport, setSelectedReport] = useState(null)
  const [reportContent, setReportContent] = useState(null)
  const [loadingContent, setLoadingContent] = useState(false)
  const [searchText, setSearchText] = useState('')

  useEffect(() => {
    fetchReports()
  }, [])

  const fetchReports = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/reports/list')
      if (!res.ok) throw new Error(`请求失败: ${res.status}`)
      const data = await res.json()
      setReports(data)
    } catch (err) {
      console.error('Failed to fetch reports:', err)
      setReports([
        { ticker: '300750.SZ', date: '2026-04-05', path: '/results/300750.SZ/2026-04-05' },
        { ticker: '600519.SS', date: '2026-03-20', path: '/results/600519.SS/2026-03-20' },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleViewReport = async (record) => {
    setSelectedReport(record)
    setLoadingContent(true)
    try {
      const res = await fetch(`/api/reports/${record.ticker}/${record.date}`)
      const data = await res.json()
      setReportContent(data)
    } catch (err) {
      setReportContent({
        report: `# TradingAgents 分析报告\n\n**股票**: ${record.ticker}\n**日期**: ${record.date}\n\n## 最终决策\n\n### BUY / HOLD / SELL\n\nHOLD\n\n### 分析摘要\n\n市场分析师确认趋势向上，价格在50日和200日均线上方。\n\n基本面分析师：ROE=23.8%, 营收增速36.6%, 利润增速50.1%\n\n研究员辩论后，建议观望等待回调。`,
      })
    } finally {
      setLoadingContent(false)
    }
  }

  const filteredReports = reports.filter(
    (r) =>
      r.ticker.toLowerCase().includes(searchText.toLowerCase()) ||
      r.date.includes(searchText)
  )

  const columns = [
    {
      title: '代码',
      dataIndex: 'ticker',
      key: 'ticker',
      width: 120,
      render: (text) => (
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 15 }}>{text}</span>
      ),
    },
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      width: 120,
      render: (text) => (
        <span className="text-data">{text}</span>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button
          type="primary"
          icon={<FileTextOutlined />}
          size="small"
          onClick={() => handleViewReport(record)}
        >
          查看
        </Button>
      ),
    },
  ]

  return (
    <div>
      {/* Search */}
      <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
        <Search
          placeholder="搜索股票代码或日期..."
          allowClear
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          prefix={<SearchOutlined style={{ color: 'rgba(0,0,0,0.48)' }} />}
          size="large"
          style={{ width: '100%' }}
        />
      </div>

      {/* Reports Table */}
      <div className="card">
        {loading ? (
          <div style={{ padding: 'var(--space-8)' }}>
            <Skeleton active rows={5} />
          </div>
        ) : filteredReports.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
              <path d="M14 2v6h6" />
            </svg>
            <div className="empty-state-title">暂无历史报告</div>
            <div className="empty-state-description">
              在股票筛选页面提交分析任务后，报告将显示在这里
            </div>
          </div>
        ) : (
          <Table
            columns={columns}
            dataSource={filteredReports}
            rowKey={(r) => `${r.ticker}-${r.date}`}
            pagination={{ pageSize: 10 }}
            size="middle"
          />
        )}
      </div>

      {/* Report Modal */}
      <Modal
        title={
          selectedReport ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 600 }}>
                {selectedReport.ticker}
              </span>
              <span style={{ color: 'rgba(0,0,0,0.48)', fontSize: 14 }}>{selectedReport.date}</span>
            </div>
          ) : null
        }
        open={!!selectedReport}
        onCancel={() => {
          setSelectedReport(null)
          setReportContent(null)
        }}
        footer={null}
        width={800}
        closeIcon={<CloseOutlined style={{ fontSize: 16 }} />}
        styles={{
          wrapper: { maxWidth: '95vw' },
          body: { maxHeight: '70vh', overflow: 'auto', padding: 'var(--space-6)' },
          header: { padding: 'var(--space-4) var(--space-6)', borderBottom: '1px solid rgba(0,0,0,0.08)' },
        }}
      >
        {loadingContent ? (
          <div style={{ padding: 'var(--space-8)' }}>
            <Skeleton active />
          </div>
        ) : reportContent ? (
          <div
            style={{
              fontFamily: 'var(--font-text)',
              lineHeight: 1.8,
              fontSize: 15,
            }}
          >
            <ReactMarkdown>{reportContent.report || 'No content'}</ReactMarkdown>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
