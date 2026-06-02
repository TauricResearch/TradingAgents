import { useEffect, useRef, useState, useCallback } from 'react'
import axios from 'axios'
import { Download, Loader2, X, RefreshCw } from 'lucide-react'
import { notify } from '../utils/notify'

interface UpdateStatus {
  git: boolean
  update_supported: boolean
  update_available: boolean
  updating: boolean
  current_short?: string | null
  latest_short?: string | null
  behind: number
  commits?: string[]
  last_update?: { state?: string; error?: string }
}

const POLL_MS = 10_000

// Global, always-visible update bar. Polls /api/update/status; when the upstream
// repo has new commits every logged-in user sees the bar and can click "Güncelle"
// to update + restart the app in place.
export default function UpdateBanner() {
  const [st, setSt] = useState<UpdateStatus | null>(null)
  const [busy, setBusy] = useState(false)        // this client triggered the update
  const [dismissed, setDismissed] = useState(false)
  const seenRef = useRef(false)                   // toast only once per availability
  const sawDownRef = useRef(false)                // saw the backend go down (= restart)
  const busyRef = useRef(false)

  useEffect(() => { busyRef.current = busy }, [busy])

  const poll = useCallback(async () => {
    try {
      const { data } = await axios.get<UpdateStatus>('/api/update/status')
      setSt(data)

      if (data.update_available && !data.updating && !seenRef.current) {
        seenRef.current = true
        notify('info', `Yeni güncelleme mevcut (${data.behind} commit).`, 'Güncelleme')
      }
      if (!data.update_available) seenRef.current = false

      // We triggered an update and it is no longer "running".
      if (busyRef.current && !data.updating) {
        if (data.last_update?.state === 'failed') {
          setBusy(false); sawDownRef.current = false
          notify('error', data.last_update?.error || 'Güncelleme başarısız oldu.', 'Güncelleme')
        } else if (sawDownRef.current && !data.update_available) {
          // The service went down (restart) and is back on the new commit → reload UI.
          window.location.reload()
        }
      }
    } catch {
      // Backend unreachable — most likely it is restarting mid-update.
      if (busyRef.current) sawDownRef.current = true
    }
  }, [])

  useEffect(() => {
    poll()
    const id = setInterval(poll, POLL_MS)
    return () => clearInterval(id)
  }, [poll])

  const doUpdate = async () => {
    if (!window.confirm('Uygulama en son sürüme güncellenip yeniden başlatılacak (~1-2 dk). Devam edilsin mi?')) return
    setBusy(true); busyRef.current = true; sawDownRef.current = false
    try {
      await axios.post('/api/update/apply')
      notify('info', 'Güncelleme başlatıldı — lütfen bekleyin, sayfa otomatik yenilenecek.', 'Güncelleme')
      poll()
    } catch (e: any) {
      setBusy(false)
      notify('error', e?.response?.data?.detail || 'Güncelleme başlatılamadı.', 'Güncelleme')
    }
  }

  if (!st || !st.update_supported) return null
  const updating = busy || st.updating
  if (!updating && (!st.update_available || dismissed)) return null

  return (
    <div
      className={`flex items-center gap-3 px-5 py-2.5 text-sm border-b ${
        updating
          ? 'bg-violet-500/10 border-violet-500/20 text-violet-200'
          : 'bg-amber-500/10 border-amber-500/20 text-amber-100'
      }`}
    >
      {updating ? <Loader2 size={15} className="animate-spin shrink-0" /> : <Download size={15} className="shrink-0 text-amber-300" />}
      <div className="flex-1 min-w-0">
        {updating ? (
          <span>Güncelleniyor — uygulama birazdan yeniden başlayacak, sayfa otomatik yenilenecek...</span>
        ) : (
          <span>
            Yeni sürüm mevcut{st.behind ? ` — ${st.behind} commit geride` : ''}.{' '}
            <span className="font-mono text-xs text-amber-300/70">{st.current_short} → {st.latest_short}</span>
          </span>
        )}
      </div>
      {!updating && (
        <>
          <button
            onClick={doUpdate}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-gray-900 font-semibold text-xs transition-colors shrink-0"
          >
            <RefreshCw size={12} /> Güncelle
          </button>
          <button onClick={() => setDismissed(true)} className="text-amber-300/60 hover:text-amber-100 transition-colors shrink-0" title="Gizle">
            <X size={15} />
          </button>
        </>
      )}
    </div>
  )
}
