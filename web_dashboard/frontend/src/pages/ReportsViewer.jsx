import { useState, useEffect, useMemo } from 'react'
import { Table, Input, Modal, Skeleton, Button, Space, message } from 'antd'
import { FileTextOutlined, SearchOutlined, CloseOutlined, DownloadOutlined } from '@ant-design/icons'
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
    } catch {
      setReports([])
    } finally {
      setLoading(false)
    }
  }

  const handleExportCsv = async () => {
    try {
      const res = await fetch('/api/reports/export')
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'tradingagents_reports.csv'; a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      message.error(e.message)
    }
  }

  const handleExportPdf = async (ticker, date) => {
    try {
      const res = await fetch(`/api/reports/${ticker}/${date}/pdf`)
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `${ticker}_${date}_report.pdf`; a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      message.error(e.message)
    }
  }

  const handleViewReport = async (record) => {
    setSelectedReport(record)
    setLoadingContent(true)
    try {
      const res = await fetch(`/api/reports/${record.ticker}/${record.date}`)
      if (!res.ok) throw new Error(`加载失败: ${res.status}`)
      const data = await res.json()
      setReportContent(data)
    } catch (err) {
      setReportContent({ report: `# 加载失败\n\n无法加载报告: ${err.message}` })
    } finally {
      setLoadingContent(false)
    }
  }

  const filteredReports = useMemo(() =>
    reports.filter(
      (r) =>
        r.ticker.toLowerCase().includes(searchText.toLowerCase()) ||
        r.date.includes(searchText)
    ),
    [reports, searchText]
  )

  const columns = useMemo(() => [
    {
      title: '代码',
      dataIndex: 'ticker',
      key: 'ticker',
      width: 120,
      render: (text) => (
        <span style={{ fontFamily: 'var(--font-ui)', fontWeight: 600, fontSize: 15 }}>{text}</span>
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
  ], [])

  return (
    <div>
      {/* Search + Export */}
      <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Search
            placeholder="搜索股票代码或日期..."
            allowClear
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
            size="large"
            style={{ flex: 1 }}
          />
          <Button icon={<DownloadOutlined />} onClick={handleExportCsv} disabled={reports.length === 0}>
            导出CSV
          </Button>
        </div>
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
              <span style={{ fontFamily: 'var(--font-ui)', fontSize: 17, fontWeight: 600 }}>
                {selectedReport.ticker}
              </span>
              <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>{selectedReport.date}</span>
            </div>
          ) : null
        }
        open={!!selectedReport}
        onCancel={() => {
          setSelectedReport(null)
          setReportContent(null)
        }}
        footer={
          selectedReport ? (
            <Space>
              <Button
                icon={<DownloadOutlined />}
                onClick={() => handleExportPdf(selectedReport.ticker, selectedReport.date)}
              >
                导出PDF
              </Button>
              <Button onClick={() => { setSelectedReport(null); setReportContent(null) }}>
                关闭
              </Button>
            </Space>
          ) : null
        }
        width={800}
        closeIcon={<CloseOutlined style={{ fontSize: 16 }} />}
        styles={{
          wrapper: { maxWidth: '95vw' },
          body: { maxHeight: '70vh', overflow: 'auto', padding: 'var(--space-6)' },
          header: { padding: 'var(--space-4) var(--space-6)', borderBottom: '1px solid var(--border)' },
        }}
      >
        {loadingContent ? (
          <div style={{ padding: 'var(--space-8)' }}>
            <Skeleton active />
          </div>
        ) : reportContent ? (
          <div
            style={{
              fontFamily: 'var(--font-ui)',
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
