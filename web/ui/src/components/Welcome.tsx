import { useState } from 'react'
import { Link } from 'react-router-dom'
import { guideSeen, markGuideSeen } from '../guideSeen'
import { MARK_CLASS } from './Help'

/** First-visit banner on the overview; gone once the guide was opened or it was dismissed. */
export function Welcome({ live }: { live: boolean }) {
  const [show, setShow] = useState(() => !guideSeen())
  if (!show) return null

  const dismiss = () => {
    markGuideSeen()
    setShow(false)
  }

  return (
    <div
      role="region"
      aria-label="新手指引"
      className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-sm border border-border border-l-2 border-l-accent bg-panel px-3 py-2"
    >
      <div className="min-w-0 flex-1 basis-[280px]">
        <div className="font-semibold">第一次来？</div>
        <p className="mt-0.5 text-muted">
          {live
            ? '这是一个由 AI 分析师团队研判、自动调仓的加密货币交易系统，你正在看的 live 账户用的是真钱。'
            : '这是一个由 AI 分析师团队每天研判、自动调仓的加密货币模拟盘。'}
          花两分钟读一下指南，知道每个数字在说什么。页面上的{' '}
          <span aria-hidden="true" className={`${MARK_CLASS} size-[14px] align-text-bottom text-[9px] text-muted`}>
            ?
          </span>{' '}
          随时能看解释。
        </p>
      </div>
      <div className="flex shrink-0 gap-2 text-[12px]">
        <Link
          to="/guide"
          className="rounded-sm border border-accent bg-accent/15 px-3 py-1 font-medium text-accent hover:bg-accent/25"
        >
          看指南
        </Link>
        <button
          type="button"
          onClick={dismiss}
          className="rounded-sm border border-border px-3 py-1 text-muted hover:border-muted hover:text-fg"
        >
          知道了
        </button>
      </div>
    </div>
  )
}
