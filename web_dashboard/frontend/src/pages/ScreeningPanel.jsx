import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Table, Button, Select, Space, Row, Col, Skeleton, Result, message, Popconfirm, Tooltip } from 'antd'
import { PlayCircleOutlined, ReloadOutlined, QuestionCircleOutlined } from '@ant-design/icons'

const SCREEN_MODES = [
  { value: 'china_strict', label: '中国严格 (China Strict)' },
  { value: 'china_relaxed', label: '中国宽松 (China Relaxed)' },
  { value: 'strict', label: '严格 (Strict)' },
  { value: 'relaxed', label: '宽松 (Relaxed)' },
  { value: 'fundamentals_only', label: '纯基本面 (Fundamentals Only)' },
]

export default function ScreeningPanel() {
  const navigate = useNavigate()
  const [mode, setMode] = useState('china_strict')
  const [loading, setLoading] = useState(true)
  const [results, setResults] = useState([])
  const [stats, setStats] = useState({ total: 0, passed: 0 })
  const [error, setError] = useState(null)

  const fetchResults = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/stocks/screen?mode=${mode}`)
      if (!res.ok) throw new Error(`请求失败: ${res.status}`)
      const data = await res.json()
      setResults(data.results || [])
      setStats({ total: data.total_stocks || 0, passed: data.passed || 0 })
    } catch (err) {
      setError(err.message)
      message.error('筛选失败: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchResults()
  }, [mode])

  const handleStartAnalysis = async (stock) => {
    try {
      const res = await fetch('/api/analysis/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: stock.ticker }),
      })
      if (!res.ok) throw new Error('启动分析失败')
      const data = await res.json()
      message.success(`已提交分析任务: ${stock.name} (${stock.ticker})`)
      navigate(`/monitor?task_id=${data.task_id}`)
    } catch (err) {
      message.error(err.message)
    }
  }

  const columns = [
    {
      title: '代码',
      dataIndex: 'ticker',
      key: 'ticker',
      width: 120,
      render: (text) => (
        <span className="text-data">{text}</span>
      ),
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 120,
      render: (text) => (
        <span style={{ fontWeight: 500 }}>{text}</span>
      ),
    },
    {
      title: (
        <Tooltip title="营业收入同比增长率">
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            营收增速 <QuestionCircleOutlined style={{ fontSize: 10, color: 'rgba(0,0,0,0.48)' }} />
          </span>
        </Tooltip>
      ),
      dataIndex: 'revenue_growth',
      key: 'revenue_growth',
      align: 'right',
      width: 100,
      render: (val) => (
        <span className="text-data" style={{ color: val > 0 ? 'var(--color-buy)' : 'var(--color-sell)' }}>
          {val?.toFixed(1)}%
        </span>
      ),
    },
    {
      title: (
        <Tooltip title="净利润同比增长率">
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            利润增速 <QuestionCircleOutlined style={{ fontSize: 10, color: 'rgba(0,0,0,0.48)' }} />
          </span>
        </Tooltip>
      ),
      dataIndex: 'profit_growth',
      key: 'profit_growth',
      align: 'right',
      width: 100,
      render: (val) => (
        <span className="text-data" style={{ color: val > 0 ? 'var(--color-buy)' : 'var(--color-sell)' }}>
          {val?.toFixed(1)}%
        </span>
      ),
    },
    {
      title: (
        <Tooltip title="净资产收益率 = 净利润/净资产">
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            ROE <QuestionCircleOutlined style={{ fontSize: 10, color: 'rgba(0,0,0,0.48)' }} />
          </span>
        </Tooltip>
      ),
      dataIndex: 'roe',
      key: 'roe',
      align: 'right',
      width: 80,
      render: (val) => (
        <span className="text-data">{val?.toFixed(1)}%</span>
      ),
    },
    {
      title: '价格',
      dataIndex: 'current_price',
      key: 'current_price',
      align: 'right',
      width: 100,
      render: (val) => (
        <span className="text-data">¥{val?.toFixed(2)}</span>
      ),
    },
    {
      title: (
        <Tooltip title="当前成交量/过去20日平均成交量">
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            Vol比 <QuestionCircleOutlined style={{ fontSize: 10, color: 'rgba(0,0,0,0.48)' }} />
          </span>
        </Tooltip>
      ),
      dataIndex: 'vol_ratio',
      key: 'vol_ratio',
      align: 'right',
      width: 80,
      render: (val) => (
        <span className="text-data">{val?.toFixed(2)}x</span>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Popconfirm
          title={`确认分析 ${record.name} (${record.ticker})？`}
          description="分析将消耗API配额，请确认。"
          onConfirm={() => handleStartAnalysis(record)}
          okText="确认"
          cancelText="取消"
        >
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            size="small"
          >
            分析
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      {/* Stats Row - Apple style */}
      <Row gutter={16} style={{ marginBottom: 'var(--space-6)' }}>
        <Col xs={24} sm={8}>
          <div className="card">
            <div className="text-caption" style={{ marginBottom: 4 }}>筛选模式</div>
            <div style={{ fontFamily: 'var(--font-text)', fontSize: 15, fontWeight: 500 }}>
              {SCREEN_MODES.find(m => m.value === mode)?.label}
            </div>
          </div>
        </Col>
        <Col xs={24} sm={8}>
          <div className="card">
            <div className="text-caption" style={{ marginBottom: 4 }}>股票总数</div>
            <div className="text-data" style={{ fontSize: 28, fontWeight: 600 }}>{stats.total}</div>
          </div>
        </Col>
        <Col xs={24} sm={8}>
          <div className="card">
            <div className="text-caption" style={{ marginBottom: 4 }}>通过数量</div>
            <div className="text-data" style={{ fontSize: 28, fontWeight: 600, color: 'var(--color-buy)' }}>{stats.passed}</div>
          </div>
        </Col>
      </Row>

      {/* Controls */}
      <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="card-header">
          <div className="card-title">SEPA 筛选</div>
          <Space>
            <Select
              value={mode}
              onChange={setMode}
              options={SCREEN_MODES}
              style={{ width: 200 }}
              popupMatchSelectWidth={false}
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchResults}
              loading={loading}
            >
              刷新
            </Button>
          </Space>
        </div>
      </div>

      {/* Results Table */}
      <div className="card">
        {loading ? (
          <Skeleton active rows={5} />
        ) : error ? (
          <Result
            status="error"
            title="加载失败"
            subTitle={error}
            extra={
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={fetchResults}
              >
                重试
              </Button>
            }
          />
        ) : results.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3v18h18M7 16l4-8 4 5 4-9" />
            </svg>
            <div className="empty-state-title">
              {stats.total > 0 ? '未找到符合条件的股票' : '请先选择筛选模式并刷新'}
            </div>
            <div className="empty-state-description">
              {stats.total > 0 ? '尝试切换筛选模式或调整参数' : '点击上方刷新按钮开始筛选'}
            </div>
          </div>
        ) : (
          <Table
            columns={columns}
            dataSource={results}
            rowKey="ticker"
            pagination={{ pageSize: 10 }}
            size="middle"
            scroll={{ x: 700 }}
          />
        )}
      </div>
    </div>
  )
}
