import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Table, Button, Input, Select, Space, Row, Col, Card, Progress, Result,
  message, Popconfirm, Modal, Tabs, Tag, Tooltip, Upload, Form, Typography,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, PlayCircleOutlined, UploadOutlined,
  DownloadOutlined, SyncOutlined, CheckCircleOutlined, CloseCircleOutlined,
  AccountBookOutlined,
} from '@ant-design/icons'
import { portfolioApi } from '../services/portfolioApi'

const { Text } = Typography

// ============== Helpers ==============

const formatMoney = (v) =>
  v == null ? '—' : `¥${v.toFixed(2)}`;

const formatPct = (v) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;

const DecisionBadge = ({ decision }) => {
  if (!decision) return null
  const cls = decision === 'BUY' ? 'badge-buy' : decision === 'SELL' ? 'badge-sell' : 'badge-hold'
  return <span className={cls}>{decision}</span>
}

// ============== Tab 1: Watchlist ==============

function WatchlistTab() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [addOpen, setAddOpen] = useState(false)
  const [form] = Form.useForm()

  const fetch_ = useCallback(async () => {
    setLoading(true)
    try {
      const res = await portfolioApi.getWatchlist()
      setData(res.watchlist || [])
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetch_() }, [fetch_])

  const handleAdd = async (vals) => {
    try {
      await portfolioApi.addToWatchlist(vals.ticker, vals.name || vals.ticker)
      message.success('已添加')
      setAddOpen(false)
      form.resetFields()
      fetch_()
    } catch (e) {
      message.error(e.message)
    }
  }

  const handleDelete = async (ticker) => {
    try {
      await portfolioApi.removeFromWatchlist(ticker)
      message.success('已移除')
      fetch_()
    } catch (e) {
      message.error(e.message)
    }
  }

  const columns = [
    { title: '代码', dataIndex: 'ticker', key: 'ticker', width: 120,
      render: t => <span className="text-data">{t}</span> },
    { title: '名称', dataIndex: 'name', key: 'name', render: t => <span style={{ fontWeight: 500 }}>{t}</span> },
    { title: '添加日期', dataIndex: 'added_at', key: 'added_at', width: 120 },
    {
      title: '操作', key: 'action', width: 100,
      render: (_, r) => (
        <Popconfirm title="确认移除？" onConfirm={() => handleDelete(r.ticker)} okText="确认" cancelText="取消">
          <Button size="small" danger icon={<DeleteOutlined />}>移除</Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="card-header">
          <div className="card-title">自选股列表</div>
          <Space>
            <Button icon={<PlusOutlined />} type="primary" onClick={() => setAddOpen(true)}>添加</Button>
            <Button icon={<SyncOutlined />} onClick={fetch_} loading={loading}>刷新</Button>
          </Space>
        </div>
      </div>

      <div className="card">
        <Table columns={columns} dataSource={data} rowKey="ticker" loading={loading} pagination={false} size="middle" />
        {data.length === 0 && !loading && (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
            </svg>
            <div className="empty-state-title">暂无自选股</div>
            <div className="empty-state-description">点击上方"添加"将股票加入自选</div>
          </div>
        )}
      </div>

      <Modal title="添加自选股" open={addOpen} onCancel={() => { setAddOpen(false); form.resetFields() }} footer={null}>
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Form.Item name="ticker" label="股票代码" rules={[{ required: true, message: '请输入股票代码' }]}>
            <Input placeholder="如 300750.SZ" />
          </Form.Item>
          <Form.Item name="name" label="名称（可选）">
            <Input placeholder="如 宁德时代" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>添加</Button>
        </Form>
      </Modal>
    </div>
  )
}

// ============== Tab 2: Positions ==============

function PositionsTab() {
  const [data, setData] = useState([])
  const [accounts, setAccounts] = useState(['默认账户'])
  const [account, setAccount] = useState(null)
  const [loading, setLoading] = useState(true)
  const [addOpen, setAddOpen] = useState(false)
  const [form] = Form.useForm()

  const fetchPositions = useCallback(async () => {
    setLoading(true)
    try {
      const [posRes, accRes] = await Promise.all([
        portfolioApi.getPositions(account),
        portfolioApi.getAccounts(),
      ])
      setData(posRes.positions || [])
      setAccounts(accRes.accounts || ['默认账户'])
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [account])

  useEffect(() => { fetchPositions() }, [fetchPositions])

  const handleAdd = async (vals) => {
    try {
      await portfolioApi.addPosition({ ...vals, account: account || '默认账户' })
      message.success('已添加')
      setAddOpen(false)
      form.resetFields()
      fetchPositions()
    } catch (e) {
      message.error(e.message)
    }
  }

  const handleDelete = async (ticker, positionId) => {
    try {
      await portfolioApi.removePosition(ticker, positionId, account)
      message.success('已移除')
      fetchPositions()
    } catch (e) {
      message.error(e.message)
    }
  }

  const handleExport = async () => {
    try {
      const blob = await portfolioApi.exportPositions(account)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'positions.csv'; a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      message.error(e.message)
    }
  }

  const totalPnl = data.reduce((s, p) => s + (p.unrealized_pnl || 0), 0)

  const columns = [
    { title: '代码', dataIndex: 'ticker', key: 'ticker', width: 110,
      render: t => <span className="text-data">{t}</span> },
    { title: '账户', dataIndex: 'account', key: 'account', width: 100 },
    { title: '数量', dataIndex: 'shares', key: 'shares', align: 'right', width: 80,
      render: v => <span className="text-data">{v}</span> },
    { title: '成本价', dataIndex: 'cost_price', key: 'cost_price', align: 'right', width: 90,
      render: v => <span className="text-data">{formatMoney(v)}</span> },
    { title: '现价', dataIndex: 'current_price', key: 'current_price', align: 'right', width: 90,
      render: v => <span className="text-data">{formatMoney(v)}</span> },
    {
      title: '浮亏浮盈',
      key: 'pnl',
      align: 'right',
      width: 110,
      render: (_, r) => {
        const pnl = r.unrealized_pnl
        const pct = r.unrealized_pnl_pct
        const color = pnl == null ? undefined : pnl >= 0 ? 'var(--color-buy)' : 'var(--color-sell)'
        return (
          <span className="text-data" style={{ color }}>
            {pnl == null ? '—' : `${pnl >= 0 ? '+' : ''}${formatMoney(pnl)}`}
            <br />
            <span style={{ fontSize: 11 }}>{pct == null ? '' : formatPct(pct)}</span>
          </span>
        )
      },
    },
    {
      title: '买入日期',
      dataIndex: 'purchase_date',
      key: 'purchase_date',
      width: 100,
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_, r) => (
        <Popconfirm title="确认平仓？" onConfirm={() => handleDelete(r.ticker, r.position_id)} okText="确认" cancelText="取消">
          <Button size="small" danger icon={<DeleteOutlined />}>平仓</Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 'var(--space-4)' }}>
        <Col xs={24} sm={12}>
          <div className="card">
            <div className="text-caption">账户</div>
            <Select
              value={account || '全部'}
              onChange={v => setAccount(v === '全部' ? null : v)}
              style={{ width: '100%' }}
              options={[{ value: '全部', label: '全部账户' }, ...accounts.map(a => ({ value: a, label: a }))]}
            />
          </div>
        </Col>
        <Col xs={24} sm={12}>
          <div className="card">
            <div className="text-caption">总浮亏浮盈</div>
            <div className="text-data" style={{ fontSize: 28, fontWeight: 600, color: totalPnl >= 0 ? 'var(--color-buy)' : 'var(--color-sell)' }}>
              {formatMoney(totalPnl)}
            </div>
          </div>
        </Col>
      </Row>

      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="card-header">
          <div className="card-title">持仓记录</div>
          <Space>
            <Button icon={<DownloadOutlined />} onClick={handleExport}>导出</Button>
            <Button icon={<PlusOutlined />} type="primary" onClick={() => setAddOpen(true)}>添加持仓</Button>
            <Button icon={<SyncOutlined />} onClick={fetchPositions} loading={loading}>刷新</Button>
          </Space>
        </div>
      </div>

      <div className="card">
        <Table columns={columns} dataSource={data} rowKey="position_id" loading={loading} pagination={false} size="middle" scroll={{ x: 700 }} />
        {data.length === 0 && !loading && (
          <div className="empty-state">
            <AccountBookOutlined style={{ fontSize: 40, color: 'rgba(0,0,0,0.2)' }} />
            <div className="empty-state-title">暂无持仓</div>
            <div className="empty-state-description">点击"添加持仓"录入您的股票仓位</div>
          </div>
        )}
      </div>

      <Modal title="添加持仓" open={addOpen} onCancel={() => { setAddOpen(false); form.resetFields() }} footer={null}>
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Form.Item name="ticker" label="股票代码" rules={[{ required: true, message: '请输入' }]}>
            <Input placeholder="300750.SZ" />
          </Form.Item>
          <Form.Item name="shares" label="数量" rules={[{ required: true, message: '请输入' }]}>
            <Input type="number" placeholder="100" />
          </Form.Item>
          <Form.Item name="cost_price" label="成本价" rules={[{ required: true, message: '请输入' }]}>
            <Input type="number" placeholder="180.50" />
          </Form.Item>
          <Form.Item name="purchase_date" label="买入日期">
            <Input placeholder="2026-01-15" />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea placeholder="可选备注" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>添加</Button>
        </Form>
      </Modal>
    </div>
  )
}

// ============== Tab 3: Recommendations ==============

function RecommendationsTab() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [taskId, setTaskId] = useState(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [progress, setProgress] = useState(null)
  const [selectedDate, setSelectedDate] = useState(null)
  const [dates, setDates] = useState([])
  const wsRef = useRef(null)

  const fetchRecs = useCallback(async (date) => {
    setLoading(true)
    try {
      const res = await portfolioApi.getRecommendations(date)
      setData(res.recommendations || [])
      if (!date) {
        const d = [...new Set((res.recommendations || []).map(r => r.analysis_date))].sort().reverse()
        setDates(d)
      }
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchRecs(selectedDate) }, [fetchRecs, selectedDate])

  const connectWs = useCallback((tid) => {
    if (wsRef.current) wsRef.current.close()
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const ws = new WebSocket(`${protocol}//${host}/ws/analysis/${tid}`)
    ws.onopen = () => setWsConnected(true)
    ws.onmessage = (e) => {
      const d = JSON.parse(e.data)
      if (d.type === 'progress') setProgress(d)
    }
    ws.onclose = () => setWsConnected(false)
    wsRef.current = ws
  }, [])

  const handleAnalyze = async () => {
    try {
      const res = await portfolioApi.startAnalysis()
      setTaskId(res.task_id)
      setAnalyzing(true)
      setProgress({ completed: 0, total: res.total, status: 'running' })
      connectWs(res.task_id)
      message.info('开始批量分析...')
    } catch (e) {
      message.error(e.message)
    }
  }

  useEffect(() => {
    if (progress?.status === 'completed' || progress?.status === 'failed') {
      setAnalyzing(false)
      setTaskId(null)
      setProgress(null)
      fetchRecs(selectedDate)
    }
  }, [progress?.status])

  useEffect(() => () => { if (wsRef.current) wsRef.current.close() }, [])

  const columns = [
    { title: '代码', dataIndex: 'ticker', key: 'ticker', width: 110,
      render: t => <span className="text-data">{t}</span> },
    { title: '名称', dataIndex: 'name', key: 'name', render: t => <span style={{ fontWeight: 500 }}>{t}</span> },
    {
      title: '决策', dataIndex: 'decision', key: 'decision', width: 80,
      render: d => <DecisionBadge decision={d} />,
    },
    { title: '分析日期', dataIndex: 'analysis_date', key: 'analysis_date', width: 120 },
  ]

  return (
    <div>
      {/* Analysis card */}
      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <div className="card-header">
          <div className="card-title">今日建议</div>
          <Space>
            {analyzing && progress && (
              <span className="text-caption">
                {wsConnected ? '🟢' : '🔴'}
                {progress.completed || 0} / {progress.total || 0}
              </span>
            )}
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleAnalyze}
              loading={analyzing}
              disabled={analyzing}
            >
              {analyzing ? '分析中...' : '生成今日建议'}
            </Button>
          </Space>
        </div>
        {analyzing && progress && (
          <Progress
            percent={Math.round(((progress.completed || 0) / (progress.total || 1)) * 100)}
            status="active"
            strokeColor="var(--color-apple-blue)"
          />
        )}
      </div>

      {/* Date filter */}
      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <Select
          allowClear
          placeholder="筛选日期"
          style={{ width: 200 }}
          value={selectedDate}
          onChange={setSelectedDate}
          options={dates.map(d => ({ value: d, label: d }))}
        />
      </div>

      {/* Recommendations list */}
      <div className="card">
        <Table columns={columns} dataSource={data} rowKey="ticker" loading={loading} pagination={{ pageSize: 10 }} size="middle" />
        {data.length === 0 && !loading && (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
            </svg>
            <div className="empty-state-title">暂无建议</div>
            <div className="empty-state-description">点击上方"生成今日建议"开始批量分析</div>
          </div>
        )}
      </div>
    </div>
  )
}

// ============== Main ==============

export default function PortfolioPanel() {
  const [activeTab, setActiveTab] = useState('watchlist')

  const items = [
    { key: 'watchlist', label: '自选股', children: <WatchlistTab /> },
    { key: 'positions', label: '持仓', children: <PositionsTab /> },
    { key: 'recommendations', label: '今日建议', children: <RecommendationsTab /> },
  ]

  return (
    <Tabs
      activeKey={activeTab}
      onChange={setActiveTab}
      items={items}
      size="large"
    />
  )
}
