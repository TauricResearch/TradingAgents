import SettingsForm from '@/features/settings/components/SettingsForm'

export default function SettingsPage() {
  return (
    <div>
      <h1
        className="text-2xl font-bold mb-1"
        style={{ color: 'var(--text-high)', fontFamily: 'var(--font-manrope)' }}
      >
        Settings
      </h1>
      <p className="text-sm mb-8" style={{ color: 'var(--text-mid)' }}>
        Configure default values for new analysis runs. API keys are managed via server environment variables.
      </p>
      <SettingsForm />
    </div>
  )
}
