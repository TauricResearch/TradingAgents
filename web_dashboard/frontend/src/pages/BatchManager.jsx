import { useState, useEffect, useCallback } from 'react'
import { Table, Button, Progress, Result, Empty, Card, message, Popconfirm, Tooltip } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, SyncOutlined, DeleteOutlined, CopyOutlined } from '@ant-design/icons'

const MAX_CONCURRENT = 3

export default function BatchManager() {
  const [tasks, setTasks] = useState([])
  const [maxConcurrent] = useState(MAX_CONCURRENT)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchTasks = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/analysis/tasks')
      if (!res.ok) throw new Error('获取任务列表失败')
      const data = await res.json()
      setTasks(data.tasks || [])
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchTasks()
    const interval = setInterval(fetchTasks, 5000)
    return () => clearInterval(interval)
  }, [fetchTasks])

  const handleCancel = async (taskId) => {
    try {
      const res = await fetch(`/api/analysis/cancel/${taskId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('取消失败')
      message.success('任务已取消')
      fetchTasks()
    } catch (err) {
      message.error(err.message)
    }
  }

  const handleRetry = async (taskId) => {
    const task = tasks.find(t => t.task_id === taskId)
    if (!task) return
    try {
      const res = await fetch('/api/analysis/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: task.ticker }),
      })
      if (!res.ok) throw new Error('重试失败')
      message.success('任务已重新提交')
      fetchTasks()
    } catch (err) {
      message.error(err.message)
    }
  }

  const handleCopyTaskId = (taskId) => {
    navigator.clipboard.writeText(taskId).then(() => {
      message.success('已复制任务ID')
    }).catch(() => {
      message.error('复制失败')
    })
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircleOutlined style={{ color: 'var(--color-buy)', fontSize: 16 }} />
      case 'failed':
        return <CloseCircleOutlined style={{ color: 'var(--color-sell)', fontSize: 16 }} />
      case 'running':
        return <SyncOutlined spin style={{ color: 'var(--color-running)', fontSize: 16 }} />
      default:
        return <span style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid rgba(0,0,0,0.2)', display: 'inline-block' }} />
    }
  }

  const getStatusTag = (status) => {
    const map = {
      pending: { text: '等待', bg: 'rgba(0,0,0,0.06)', color: 'rgba(0,0,0,0.48)' },
      running: { text: '分析中', bg: 'rgba(168,85,247,0.12)', color: 'var(--color-running)' },
      completed: { text: '完成', bg: 'rgba(34,197,94,0.12)', color: 'var(--color-buy)' },
      failed: { text: '失败', bg: 'rgba(220,38,38,0.12)', color: 'var(--color-sell)' },
    }
    const s = map[status] || map.pending
    return (
      <span style={{ background: s.bg, color: s.color, padding: '2px 10px', borderRadius: 'var(--radius-pill)', fontSize: 12, fontWeight: 600 }}>
        {s.text}
      </span>
    )
  }

  const getDecisionBadge = (decision) => {
    if (!decision) return null
    const cls = decision === 'BUY' ? 'badge-buy' : decision === 'SELL' ? 'badge-sell' : 'badge-hold'
    return <span className={cls}>{decision}</span>
  }

  const columns = [
    {
      title: '状态',
      key: 'status',
      width: 110,
      render: (_, record) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {getStatusIcon(record.status)}
          {getStatusTag(record.status)}
        </div>
      ),
    },
    {
      title: '股票',
      dataIndex: 'ticker',
      key: 'ticker',
      render: (text) => (
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 15 }}>{text}</span>
      ),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 140,
      render: (val, record) =>
        record.status === 'running' || record.status === 'pending' ? (
          <Progress
            percent={val || 0}
            size="small"
            strokeColor="var(--color-apple-blue)"
            trailColor="rgba(0,0,0,0.08)"
          />
        ) : (
          <span className="text-data">{val || 0}%</span>
        ),
    },
    {
      title: '决策',
      dataIndex: 'decision',
      key: 'decision',
      width: 80,
      render: getDecisionBadge,
    },
    {
      title: '任务ID',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 220,
      render: (text) => (
        <Tooltip title={text} placement="topLeft">
          <span className="text-data" style={{ fontSize: 11, color: 'rgba(0,0,0,0.48)', cursor: 'default' }}>
            {text.slice(0, 18)}...
          </span>
          <button
            onClick={(e) => { e.stopPropagation(); handleCopyTaskId(text) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px', color: 'rgba(0,0,0,0.48)', display: 'inline-flex', alignItems: 'center' }}
            title="复制任务ID"
          >
            <CopyOutlined style={{ fontSize: 12 }} />
          </button>
        </Tooltip>
      ),
    },
    {
      title: '错误',
      dataIndex: 'error',
      key: 'error',
      width: 180,
      ellipsis: { showTitle: false },
      render: (error) =>
        error ? (
          <Tooltip title={error} placement="topLeft">
            <span style={{ color: 'var(--color-sell)', fontSize: 12, display: 'block' }}>{error}</span>
          </Tooltip>
        ) : null,
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, record) => (
        <div style={{ display: 'flex', gap: 8 }}>
          {record.status === 'running' && (
            <Popconfirm
              title="确认取消此任务？"
              onConfirm={() => handleCancel(record.task_id)}
              okText="确认"
              cancelText="取消"
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                取消
              </Button>
            </Popconfirm>
          )}
          {record.status === 'failed' && (
            <Button size="small" icon={<SyncOutlined />} onClick={() => handleRetry(record.task_id)}>
              重试
            </Button>
          )}
        </div>
      ),
    },
  ]

  const pendingCount = tasks.filter(t => t.status === 'pending').length
  const runningCount = tasks.filter(t => t.status === 'running').length
  const completedCount = tasks.filter(t => t.status === 'completed').length
  const failedCount = tasks.filter(t => t.status === 'failed').length

  return (
    <div>
      {/* Stats */}
      <div style={{ display: 'flex', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}>
        <Card size="small" className="card" style={{ flex: 1 }}>
          <div className="text-data" style={{ fontSize: 32, fontWeight: 600 }}>{pendingCount}</div>
          <div className="text-caption">等待中</div>
        </Card>
        <Card size="small" className="card" style={{ flex: 1 }}>
          <div className="text-data" style={{ fontSize: 32, fontWeight: 600, color: 'var(--color-running)' }}>{runningCount}</div>
          <div className="text-caption">分析中</div>
        </Card>
        <Card size="small" className="card" style={{ flex: 1 }}>
          <div className="text-data" style={{ fontSize: 32, fontWeight: 600, color: 'var(--color-buy)' }}>{completedCount}</div>
          <div className="text-caption">已完成</div>
        </Card>
        <Card size="small" className="card" style={{ flex: 1 }}>
          <div className="text-data" style={{ fontSize: 32, fontWeight: 600, color: 'var(--color-sell)' }}>{failedCount}</div>
          <div className="text-caption">失败</div>
        </Card>
      </div>

      {/* Tasks Table */}
      <div className="card">
        {loading && tasks.length === 0 ? (
          <div style={{ padding: 'var(--space-8)', textAlign: 'center' }}>
            <div className="loading-pulse">加载中...</div>
          </div>
        ) : error && tasks.length === 0 ? (
          <Result
            status="error"
            title="加载失败"
            subTitle={error}
            extra={
              <Button type="primary" onClick={fetchTasks}>
                重试
              </Button>
            }
          />
        ) : tasks.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="4" y="4" width="6" height="6" rx="1" />
              <rect x="14" y="4" width="6" height="6" rx="1" />
              <rect x="4" y="14" width="6" height="6" rx="1" />
              <rect x="14" y="14" width="6" height="6" rx="1" />
            </svg>
            <div className="empty-state-title">暂无批量任务</div>
            <div className="empty-state-description">
              在股票筛选页面提交分析任务
            </div>
            <button
              className="btn-primary"
              style={{ marginTop: 'var(--space-4)' }}
              onClick={() => window.location.href = '/'}
            >
              去筛选
            </button>
          </div>
        ) : (
          <Table
            columns={columns}
            dataSource={tasks}
            rowKey="task_id"
            pagination={false}
            size="middle"
          />
        )}
      </div>
    </div>
  )
}
