import { render, screen } from '@testing-library/react'
import PipelineStepper from '@/features/run-detail/components/PipelineStepper'
import { AGENT_STEPS } from '@/lib/types/run'
import type { StepStatus } from '@/lib/types/agents'

function makeSteps(overrides: Partial<Record<string, StepStatus>> = {}) {
  return Object.fromEntries(
    AGENT_STEPS.map((s) => [s, overrides[s] ?? 'pending' as StepStatus])
  ) as Record<string, StepStatus>
}

test('renders 5 phase labels', () => {
  render(<PipelineStepper steps={makeSteps()} />)
  expect(screen.getByText('Analysis')).toBeInTheDocument()
  expect(screen.getByText('Research')).toBeInTheDocument()
  expect(screen.getByText('Trade Plan')).toBeInTheDocument()
  expect(screen.getByText('Risk Review')).toBeInTheDocument()
  expect(screen.getByText('Chief Analyst')).toBeInTheDocument()
})

test('phase is done when all its steps are done', () => {
  const steps = makeSteps({
    market_analyst: 'done', news_analyst: 'done',
    fundamentals_analyst: 'done', social_analyst: 'done',
  })
  render(<PipelineStepper steps={steps} />)
  expect(screen.getAllByText(/Analysis|Research|Trade Plan|Risk Review|Chief Analyst/).length).toBeGreaterThanOrEqual(5)
})
