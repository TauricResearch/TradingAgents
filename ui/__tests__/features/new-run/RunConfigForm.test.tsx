import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import RunConfigForm from '@/features/new-run/components/RunConfigForm'

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: mockPush }) }))
jest.mock('@/lib/api-client', () => ({
  createRun: jest.fn().mockResolvedValue({ id: 'test123' }),
}))

test('renders ticker and date inputs', () => {
  render(<RunConfigForm />)
  expect(screen.getByPlaceholderText('e.g. NVDA')).toBeInTheDocument()
  expect(screen.getByLabelText(/trade date/i)).toBeInTheDocument()
})

test('submitting navigates to run detail page', async () => {
  render(<RunConfigForm />)
  fireEvent.change(screen.getByPlaceholderText('e.g. NVDA'), {
    target: { value: 'NVDA' },
  })
  fireEvent.change(screen.getByLabelText(/trade date/i), {
    target: { value: '2024-05-10' },
  })
  fireEvent.click(screen.getByText(/run analysis/i))
  await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/runs/test123'))
})
