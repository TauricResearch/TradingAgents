import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Card, Progress, Badge, Empty, Button, Result, message } from 'antd'
import DecisionBadge from '../components/DecisionBadge'
import ContractCues from '../components/ContractCues'
import { StatusIcon } from '../components/StatusIcon'
import {
  getConfidence,
  getDecision,
  getDisplayDate,
  getErrorMessage,
  getLlmSignal,
  getQuantSignal,
  isCompletedLikeStatus,
} from '../utils/contractView'

const ANALYSIS_STAGES = [
  { key: 'analysts', label: '分析师团队' },
  { key: 'research', label: '研究员辩论' },
  { key: 'trading', label: '交易员' },
  { key: 'risk', label: '风险管理' },
  { key: 'portfolio', label: '组合经理' },
]

export default function AnalysisMonitor() {
  const [searchParams] = useSearchParams()
  const taskId = searchParams.get('task_id')
  const [task, setTask] = useState(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const wsRef = useRef(null)
  const decision = getDecision(task)
  const llmSignal = getLlmSignal(task)
  const quantSignal = getQuantSignal(task)
  const confidence = getConfidence(task)
  const displayDate = getDisplayDate(task)
  const errorMessage = getErrorMessage(task)

  const fetchInitialState = useCallback(async () => {
    if (!taskId) return
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
        // ignore parse errors
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

  if (!taskId) {
    return (
      <div className="card">
        <div className="empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
          <div className="empty-state-title">暂无分析任务</div>
          <div className="empty-state-description">
            在股票筛选页面选择股票并点击"分析"开始
          </div>
          <button
            className="btn-primary"
            style={{ marginTop: 'var(--space-4)' }}
            onClick={() => window.location.href = '/'}
          >
            去筛选
          </button>
        </div>
      </div>
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
            <span style={{ fontFamily: 'var(--font-ui)', fontSize: 17, fontWeight: 600 }}>
              当前分析任务
            </span>
            <Badge
              status={error ? 'error' : wsConnected ? 'success' : 'default'}
              text={
                <span style={{ fontSize: 12, color: error ? 'var(--sell)' : wsConnected ? 'var(--buy)' : 'var(--text-muted)' }}>
                  {error ? '错误' : wsConnected ? '实时连接' : '连接中'}
                </span>
              }
            />
          </div>
        }
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
            <div className="loading-pulse" style={{ fontSize: 16 }}>连接中...</div>
          </div>
        ) : error && !task ? (
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
                <span style={{ fontFamily: 'var(--font-ui)', fontSize: 28, fontWeight: 600, letterSpacing: 0.196, lineHeight: 1.14 }}>
                  {task.ticker}
                </span>
                <DecisionBadge decision={decision} />
              </div>
              {displayDate && (
                <div style={{ marginBottom: 10, fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                  分析日期: {displayDate}
                </div>
              )}

              {/* Signal Detail Row */}
              {isCompletedLikeStatus(task.status) && (llmSignal || quantSignal || confidence != null) && (
                <div style={{ display: 'flex', gap: 24, marginBottom: 12, fontSize: 'var(--text-sm)', fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>
                  {llmSignal && (
                    <span>LLM: <DecisionBadge decision={llmSignal} /></span>
                  )}
                  {quantSignal && (
                    <span>Quant: <DecisionBadge decision={quantSignal} /></span>
                  )}
                  {confidence != null && (
                    <span>置信度: <strong style={{ color: 'var(--text-primary)' }}>{(confidence * 100).toFixed(0)}%</strong></span>
                  )}
                </div>
              )}
              <ContractCues payload={task} style={{ marginBottom: 12 }} />
              {errorMessage && (
                <div style={{ marginBottom: 12, fontSize: 'var(--text-sm)', color: 'var(--sell)' }}>
                  错误: {errorMessage}
                </div>
              )}

              {/* Progress */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
                <div className="progress-bar" style={{ flex: 1, height: 6 }}>
                  <div className="progress-bar-fill" style={{ width: `${task.progress || 0}%` }} />
                </div>
                <span className="text-data" style={{ minWidth: 50, textAlign: 'right' }}>
                  {task.progress || 0}%
                </span>
              </div>
            </div>

            {/* Stages */}
            <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginBottom: 'var(--space-6)' }}>
              {ANALYSIS_STAGES.map((stage, index) => {
                const stageState = task.stages?.[index]
                const status = stageState?.status || 'pending'
                return (
                  <div key={stage.key} className={`stage-pill ${status}`}>
                    <StatusIcon status={status} />
                    <span>{stage.label}</span>
                  </div>
                )
              })}
            </div>

            {/* Logs */}
            <div>
              <div className="text-caption" style={{ marginBottom: 12, textTransform: 'uppercase', fontWeight: 600 }}>
                实时日志
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-data)',
                  fontSize: 12,
                  background: 'var(--bg-elevated)',
                  padding: 'var(--space-4)',
                  borderRadius: 'var(--radius-standard)',
                  maxHeight: 280,
                  overflow: 'auto',
                }}
              >
                {task.logs?.length > 0 ? (
                  task.logs.map((log, i) => (
                    <div key={i} style={{ marginBottom: 8, lineHeight: 1.4 }}>
                      <span style={{ color: 'var(--text-muted)' }}>[{log.time}]</span>{' '}
                      <span style={{ fontWeight: 500 }}>{log.stage}:</span>{' '}
                      <span>{log.message}</span>
                    </div>
                  ))
                ) : (
                  <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-4)' }}>
                    等待日志输出...
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="empty-state">
            <div className="empty-state-title">暂无任务数据</div>
          </div>
        )}
      </Card>
    </div>
  )
}
