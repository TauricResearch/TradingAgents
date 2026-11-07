/**
 * The beginner's guide: one section per topic, in reading order.
 *
 * A body is Markdown. It may use `{{name}}` placeholders, filled from the strategy
 * the API reports (see `strategyVars` in `content/vars.ts`), so the numbers in the
 * guide always match the code that trades.
 */

export type GuideSectionId =
  | 'what'
  | 'daily-cycle'
  | 'research'
  | 'sizing'
  | 'risk'
  | 'perps'
  | 'overview-page'
  | 'research-page'
  | 'history-page'
  | 'validation'
  | 'glossary'
  | 'faq'

export interface GuideSection {
  id: GuideSectionId
  title: string
  body: string
}

export const GUIDE: GuideSection[] = [
  { id: 'what', title: '这是什么', body: '' },
  { id: 'daily-cycle', title: '每天发生什么', body: '' },
  { id: 'research', title: '研判是怎么做出来的', body: '' },
  { id: 'sizing', title: '评级怎么变成仓位', body: '' },
  { id: 'risk', title: '风控：止损、熔断、成本', body: '' },
  { id: 'perps', title: '永续合约小知识', body: '' },
  { id: 'overview-page', title: '怎么读「总览」', body: '' },
  { id: 'research-page', title: '怎么读「研判」', body: '' },
  { id: 'history-page', title: '怎么读「历史」', body: '' },
  { id: 'validation', title: '验证期与对照组合', body: '' },
  { id: 'glossary', title: '术语表', body: '' },
  { id: 'faq', title: '常见问题', body: '' },
]
