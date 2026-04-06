import { useState, useEffect, useCallback } from 'react'
import { Table, Button, Tag, Progress, Result, Empty, Tabs, InputNumber, Card, Skeleton, message } from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons'

const MAX_CONCURRENT = 3

export default function BatchManager() {
  const [tasks, setTasks] = useState([])
  const [maxConcurrent, setMaxConcurrent] = useState(MAX_CONCURRENT)
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

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircleOutlined style={{ color: 'var(--color-buy)' }} />
      case 'running':
        return <SyncOutlined spin style={{ color: 'var(--color-running)' }} />
      case 'failed':
        return <CloseCircleOutlined style={{ color: 'var(--color-sell)' }} />
      default:
        return <PauseCircleOutlined style={{ color: 'var(--color-hold)' }} />
    }
  }

  const getDecisionBadge = (decision) => {
    if (!decision) return null
    const colorMap = {
      BUY: 'var(--color-buy)',
      SELL: 'var(--color-sell)',
      HOLD: 'var(--color-hold)',
    }
    return (
      <Tag
        color={colorMap[decision]}
        style={{ fontFamily: 'var(--font-data)', fontWeight: 600 }}
      >
        {decision}
      </Tag>
    )
  }

  const getStatusTag = (task) => {
    const statusMap = {
      pending: { text: '等待', color: 'var(--color-hold)' },
      running: { text: '分析中', color: 'var(--color-running)' },
      completed: { text: '完成', color: 'var(--color-buy)' },
      failed: { text: '失败', color: 'var(--color-sell)' },
    }
    const s = statusMap[task.status]
    return (
      <Tag style={{ background: `${s.color}20`, color: s.color, border: 'none' }}>
        {s.text}
      </Tag>
    )
  }

  const columns = [
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_, record) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {getStatusIcon(record.status)}
          {getStatusTag(record)}
        </div>
      ),
    },
    {
      title: '股票',
      key: 'stock',
      render: (_, record) => (
        <div>
          <div style={{ fontWeight: 500 }}>{record.ticker}</div>
        </div>
      ),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 150,
      render: (val, record) =>
        record.status === 'running' || record.status === 'pending' ? (
          <Progress
            percent={val}
            size="small"
            strokeColor={
              record.status === 'pending'
                ? 'var(--color-hold)'
                : 'var(--color-running)'
            }
          />
        ) : (
          <span style={{ fontFamily: 'var(--font-data)' }}>{val}%</span>
        ),
    },
    {
      title: '决策',
      dataIndex: 'decision',
      key: 'decision',
      width: 80,
      render: (decision) => getDecisionBadge(decision),
    },
    {
      title: '任务ID',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 200,
      render: (text) => (
        <span style={{ fontFamily: 'var(--font-data)', fontSize: 12, color: 'var(--color-text-muted)' }}>{text}</span>
      ),
    },
    {
      title: '错误',
      dataIndex: 'error',
      key: 'error',
      render: (error) =>
        error ? (
          <span style={{ color: 'var(--color-sell)', fontSize: 12 }}>{error}</span>
        ) : null,
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_, record) => (
        <div style={{ display: 'flex', gap: 8 }}>
          {record.status === 'running' && (
            <Button
              size="small"
              danger
              icon={<PauseCircleOutlined />}
              onClick={() => handleCancel(record.task_id)}
              aria-label="取消"
            >
              取消
            </Button>
          )}
          {record.status === 'failed' && (
            <Button
              size="small"
              icon={<SyncOutlined />}
              onClick={() => handleRetry(record.task_id)}
              aria-label="重试"
            >
              重试
            </Button>
          )}
        </div>
      ),
    },
  ]

  const pendingCount = tasks.filter((t) => t.status === 'pending').length
  const runningCount = tasks.filter((t) => t.status === 'running').length
  const completedCount = tasks.filter((t) => t.status === 'completed').length
  const failedCount = tasks.filter((t) => t.status === 'failed').length

  return (
    <div>
      {/* Stats */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 'var(--space-6)' }}>
        <Card size="small" className="card" style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 24, fontWeight: 600 }}>
            {pendingCount}
          </div>
          <div style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>等待中</div>
        </Card>
        <Card size="small" className="card" style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 24, fontWeight: 600, color: 'var(--color-running)' }}>
            {runningCount}
          </div>
          <div style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>分析中</div>
        </Card>
        <Card size="small" className="card" style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 24, fontWeight: 600, color: 'var(--color-buy)' }}>
            {completedCount}
          </div>
          <div style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>已完成</div>
        </Card>
        <Card size="small" className="card" style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: 24, fontWeight: 600, color: 'var(--color-sell)' }}>
            {failedCount}
          </div>
          <div style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>失败</div>
        </Card>
      </div>

      {/* Settings */}
      <Card size="small" className="card" style={{ marginBottom: 'var(--space-6)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span>最大并发数:</span>
          <InputNumber
            min={1}
            max={10}
            value={maxConcurrent}
            onChange={(val) => setMaxConcurrent(val)}
            style={{ width: 80 }}
          />
          <span style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>
            同时运行的分析任务数量
          </span>
        </div>
      </Card>

      {/* Tasks Table */}
      <div className="card">
        {loading ? (
          <Skeleton active rows={5} />
        ) : error ? (
          <Result
            status="error"
            title="加载失败"
            description="点击重试按钮重新加载数据"
            subTitle={error}
            extra={
              <Button
                type="primary"
                onClick={() => {
                  fetchTasks()
                }}
                aria-label="重试"
              >
                重试
              </Button>
            }
          />
        ) : tasks.length === 0 ? (
          <Empty
            description="暂无批量任务"
            image={
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ width: 48, height: 48 }}>
                <rect x="4" y="4" width="6" height="6" rx="1" />
                <rect x="14" y="4" width="6" height="6" rx="1" />
                <rect x="4" y="14" width="6" height="6" rx="1" />
                <rect x="14" y="14" width="6" height="6" rx="1" />
              </svg>
            }
          />
        ) : (
          <Table
            columns={columns}
            dataSource={tasks}
            rowKey="id"
            pagination={false}
          />
        )}
      </div>
    </div>
  )
}
