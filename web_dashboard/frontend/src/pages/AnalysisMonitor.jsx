import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Card, Progress, Timeline, Badge, Empty, Button, Tag, Result, message } from 'antd'
import { CheckCircleOutlined, SyncOutlined, CloseCircleOutlined } from '@ant-design/icons'

const ANALYSIS_STAGES = [
  { key: 'analysts', label: '分析师团队', description: 'Market / Social / News / Fundamentals' },
  { key: 'research', label: '研究员辩论', description: 'Bull vs Bear Researcher debate' },
  { key: 'trader', label: '交易员', description: 'Compose investment plan' },
  { key: 'risk', label: '风险管理', description: 'Aggressive vs Conservative vs Neutral' },
  { key: 'portfolio', label: '组合经理', description: 'Final BUY/HOLD/SELL decision' },
]

export default function AnalysisMonitor() {
  const [searchParams] = useSearchParams()
  const taskId = searchParams.get('task_id')
  const [task, setTask] = useState(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const wsRef = useRef(null)

  const fetchInitialState = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`/api/analysis/status/${taskId}`)
      if (!res.ok) throw new Error('获取任务状态失败')
      const data = await res.json()
      setTask(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [taskId])

  const connectWebSocket = useCallback(() => {
    if (wsRef.current) wsRef.current.close()
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const ws = new WebSocket(`${protocol}//${host}/ws/analysis/${taskId}`)

    ws.onopen = () => {
      setWsConnected(true)
      setError(null)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'progress') {
          const { type, ...taskData } = data
          setTask(taskData)
        }
      } catch (e) {
        // Ignore parse errors
      }
    }

    ws.onerror = () => {
      setError('WebSocket连接失败')
      setWsConnected(false)
    }

    ws.onclose = () => {
      setWsConnected(false)
    }

    wsRef.current = ws
  }, [taskId])

  useEffect(() => {
    if (!taskId) return
    fetchInitialState()
    connectWebSocket()
    return () => {
      if (wsRef.current) wsRef.current.close()
    }
  }, [taskId, fetchInitialState, connectWebSocket])

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const getStageStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircleOutlined style={{ color: 'var(--color-buy)' }} />
      case 'running':
        return <SyncOutlined spin style={{ color: 'var(--color-running)' }} />
      case 'failed':
        return <CloseCircleOutlined style={{ color: 'var(--color-sell)' }} />
      default:
        return <Badge status="default" />
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
        style={{
          fontFamily: 'var(--font-data)',
          fontWeight: 600,
          fontSize: 14,
          padding: '4px 12px',
        }}
      >
        {decision}
      </Tag>
    )
  }

  return (
    <div>
      {/* Current Task Card */}
      <Card
        className="card"
        style={{ marginBottom: 'var(--space-6)' }}
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span>当前分析任务</span>
            <Badge
              status={error ? 'error' : wsConnected ? 'success' : 'error'}
              text={error ? '错误' : wsConnected ? '实时连接' : '未连接'}
            />
          </div>
        }
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
            <div className="loading-pulse" style={{ color: 'var(--color-running)', fontSize: 16 }}>
              连接中...
            </div>
          </div>
        ) : error ? (
          <Result
            status="error"
            title="连接失败"
            subTitle={error}
            extra={
              <Button
                type="primary"
                onClick={() => {
                  fetchInitialState()
                  connectWebSocket()
                }}
                aria-label="重新连接"
              >
                重新连接
              </Button>
            }
          />
        ) : task ? (
          <>
            {/* Task Header */}
            <div style={{ marginBottom: 'var(--space-6)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
                <span style={{ fontSize: 24, fontWeight: 600 }}>{task.name}</span>
                <span style={{ fontFamily: 'var(--font-data)', color: 'var(--color-text-muted)' }}>
                  {task.ticker}
                </span>
                {getDecisionBadge(task.decision)}
              </div>

              {/* Progress */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <Progress
                  percent={task.progress}
                  status="active"
                  strokeColor="var(--color-buy)"
                  style={{ flex: 1 }}
                />
                <span
                  style={{
                    fontFamily: 'var(--font-data)',
                    color: 'var(--color-text-muted)',
                    minWidth: 50,
                  }}
                >
                  {formatTime(task.elapsed)}
                </span>
              </div>
            </div>

            {/* Stages */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 24 }}>
              {ANALYSIS_STAGES.map((stage, index) => (
                <div
                  key={stage.key}
                  style={{
                    padding: '8px 16px',
                    background:
                      task.stages[index]?.status === 'running'
                        ? 'rgba(168, 85, 247, 0.15)'
                        : task.stages[index]?.status === 'completed'
                        ? 'rgba(34, 197, 94, 0.15)'
                        : 'var(--color-surface-elevated)',
                    borderRadius: 'var(--radius-md)',
                    border: `1px solid ${
                      task.stages[index]?.status === 'running'
                        ? 'var(--color-running)'
                        : task.stages[index]?.status === 'completed'
                        ? 'var(--color-buy)'
                        : 'var(--color-border)'
                    }`,
                    opacity: task.stages[index]?.status === 'pending' ? 0.5 : 1,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {getStageStatusIcon(task.stages[index]?.status)}
                    <span>{stage.label}</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Logs */}
            <div>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--color-text-muted)',
                  marginBottom: 12,
                  textTransform: 'uppercase',
                }}
              >
                实时日志
              </div>
              <div
                aria-live="polite"
                style={{
                  fontFamily: 'var(--font-data)',
                  fontSize: 12,
                  background: 'var(--color-bg)',
                  padding: 'var(--space-4)',
                  borderRadius: 'var(--radius-md)',
                  maxHeight: 300,
                  overflow: 'auto',
                }}
              >
                {task.logs.map((log, i) => (
                  <div key={i} style={{ marginBottom: 8 }}>
                    <span style={{ color: 'var(--color-text-muted)' }}>[{log.time}]</span>{' '}
                    <span style={{ color: 'var(--color-interactive)' }}>{log.stage}:</span>{' '}
                    <span>{log.message}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <Empty description="暂无进行中的分析任务" image={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ width: 48, height: 48 }}>
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
          } />
        )}
      </Card>

      {/* No Active Task */}
      {!task && (
        <div className="card">
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
            <div className="empty-state-title">暂无进行中的分析</div>
            <div className="empty-state-description">
              在股票筛选页面选择股票并点击"分析"开始
            </div>
            <Button type="primary" style={{ marginTop: 16 }} aria-label="去筛选股票">
              去筛选股票
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
