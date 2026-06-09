import { createI18n } from 'vue-i18n'

// Ported from webui.py LANG (en/zh), scoped to what the SPA renders.
const messages = {
  en: {
    title: 'TradingAgents',
    subtitle: 'Multi-agent LLM trading framework',
    nav: { analysis: 'Analysis', history: 'History', settings: 'Settings', signOut: 'Sign out' },
    login: {
      caption: 'Restricted access. Enter your email to receive a one-time code.',
      email: 'Email address', sendCode: 'Send code', code: 'Verification code',
      verify: 'Verify', useOther: 'Use a different email',
      invalid: 'Invalid or expired code. Try again or request a new one.',
      sent: 'A 6-digit code was sent to {email}. It expires in 10 minutes.',
    },
    cfg: {
      ticker: 'Ticker / company name', date: 'Analysis date', provider: 'LLM provider',
      deepModel: 'Deep-think model', quickModel: 'Quick-think model',
      analysts: 'Analysts', market: 'Market / Technical', social: 'Social / Sentiment',
      news: 'News & Macro', fundamentals: 'Fundamentals',
      debateRounds: 'Bull/Bear debate rounds', riskRounds: 'Risk discussion rounds',
      outputLang: 'Report output language', checkpoint: 'Enable checkpoint resume',
      keyLoaded: '{env} loaded ✓', keyMissing: '{env} not set — add it to .env',
      resolvedAs: '→ resolved as', run: 'Run analysis', cancel: 'Cancel run',
    },
    tabs: {
      market: 'Market', sentiment: 'Sentiment', news: 'News', fundamentals: 'Fundamentals',
      invest: 'Investment Plan', trader: 'Trader', risk: 'Risk Decision', log: 'Activity log',
    },
    status: { pending: 'Pending', running: 'Running', done: 'Complete', error: 'Error' },
    elapsed: 'Elapsed', waiting: 'waiting…',
    settings: {
      schedule: 'Daily schedule', enable: 'Enable daily analysis', watchlist: 'Watchlist (one per line)',
      chatId: 'Telegram chat_id', testPing: 'Send test ping', research: 'Research notes',
      upload: 'Upload (PDF / MD / TXT)', defaults: 'Default preferences', save: 'Save',
      saved: 'Saved.',
    },
    history: { title: 'Past runs', empty: 'No past runs yet.', open: 'Open' },
  },
  zh: {
    title: 'TradingAgents',
    subtitle: '多智能体 LLM 交易框架',
    nav: { analysis: '分析', history: '历史', settings: '设置', signOut: '退出' },
    login: {
      caption: '受限访问。请输入邮箱以接收一次性验证码。',
      email: '邮箱地址', sendCode: '发送验证码', code: '验证码', verify: '验证',
      useOther: '换个邮箱', invalid: '验证码错误或已过期，请重试或重新发送。',
      sent: '已向 {email} 发送 6 位验证码，10 分钟内有效。',
    },
    cfg: {
      ticker: '股票代码 / 公司名', date: '分析日期', provider: 'LLM 厂商',
      deepModel: '深度思考模型', quickModel: '快速思考模型',
      analysts: '分析师', market: '市场 / 技术', social: '社交 / 情绪',
      news: '新闻 & 宏观', fundamentals: '基本面',
      debateRounds: '多空辩论轮数', riskRounds: '风险讨论轮数',
      outputLang: '报告输出语言', checkpoint: '启用断点续跑',
      keyLoaded: '已加载 {env} ✓', keyMissing: '{env} 未设置 — 请加到 .env',
      resolvedAs: '→ 解析为', run: '开始分析', cancel: '取消运行',
    },
    tabs: {
      market: '市场', sentiment: '情绪', news: '新闻', fundamentals: '基本面',
      invest: '投资计划', trader: '交易员', risk: '风险决策', log: '活动日志',
    },
    status: { pending: '等待中', running: '运行中', done: '完成', error: '错误' },
    elapsed: '已用时', waiting: '等待中…',
    settings: {
      schedule: '每日定时分析', enable: '启用每日分析', watchlist: '自选股（每行一个）',
      chatId: 'Telegram chat_id', testPing: '发送测试消息', research: '研究笔记',
      upload: '上传（PDF / MD / TXT）', defaults: '默认偏好', save: '保存', saved: '已保存。',
    },
    history: { title: '历史运行', empty: '暂无历史运行。', open: '打开' },
  },
}

const saved = (typeof localStorage !== 'undefined' && localStorage.getItem('ui_lang')) || 'en'

export const i18n = createI18n({
  legacy: false,
  locale: saved === 'zh' ? 'zh' : 'en',
  fallbackLocale: 'en',
  messages,
})

export function setLocale(l: 'en' | 'zh') {
  i18n.global.locale.value = l
  if (typeof localStorage !== 'undefined') localStorage.setItem('ui_lang', l)
}
