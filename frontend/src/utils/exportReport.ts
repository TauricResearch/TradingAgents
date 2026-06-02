export interface AnalysisForExport {
  ticker: string
  trade_date: string
  signal: string | null
  market_report?: string
  sentiment_report?: string
  news_report?: string
  fundamentals_report?: string
  macro_report?: string
  options_report?: string
  quant_report?: string
  earnings_report?: string
  review_report?: string
  investment_plan?: string
  trader_plan?: string
  final_decision?: string
}

const LABELS: Record<string, string> = {
  market_report: 'Piyasa Analizi', sentiment_report: 'Duygu Analizi',
  news_report: 'Haber Analizi', fundamentals_report: 'Temel Analiz',
  macro_report: 'Makro Analiz', options_report: 'Opsiyon Analizi',
  quant_report: 'Kantitatif Analiz', earnings_report: 'Kazanç Analizi',
  review_report: 'Performans İnceleme', investment_plan: 'Yatırım Planı',
  trader_plan: 'Trader Planı', final_decision: 'PM Kararı',
}

export function exportMarkdown(analysis: AnalysisForExport): void {
  const lines: string[] = [
    `# ${analysis.ticker} — Analiz Raporu`,
    `**Tarih:** ${analysis.trade_date}  `,
    `**Sinyal:** ${analysis.signal ?? 'N/A'}`,
    '',
    '---',
    '',
  ]

  for (const [key, label] of Object.entries(LABELS)) {
    const content = (analysis as any)[key]
    if (content) {
      lines.push(`## ${label}`, '', content.trim(), '', '---', '')
    }
  }

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${analysis.ticker}_${analysis.trade_date}.md`
  a.click()
  URL.revokeObjectURL(url)
}

export function exportPDF(analysis: AnalysisForExport): void {
  const content = buildTextContent(analysis)
  // Build plain-text PDF using browser print dialog (no external dep needed)
  const win = window.open('', '_blank')
  if (!win) return
  win.document.write(`
    <html><head>
    <title>${analysis.ticker} ${analysis.trade_date}</title>
    <style>
      body { font-family: monospace; font-size: 12px; padding: 24px; white-space: pre-wrap; }
      h1 { font-size: 18px; } h2 { font-size: 14px; margin-top: 20px; border-top: 1px solid #ccc; padding-top: 8px; }
    </style></head>
    <body>${content}</body></html>
  `)
  win.document.close()
  win.print()
}

function buildTextContent(analysis: AnalysisForExport): string {
  let html = `<h1>${analysis.ticker} — ${analysis.trade_date} — ${analysis.signal ?? 'N/A'}</h1>`
  for (const [key, label] of Object.entries(LABELS)) {
    const content = (analysis as any)[key]
    if (content) {
      html += `<h2>${label}</h2><p>${escapeHtml(content.trim())}</p>`
    }
  }
  return html
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
}
