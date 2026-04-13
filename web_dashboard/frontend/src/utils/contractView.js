export function getCompat(payload) {
  return payload?.compat || {}
}

export function getResult(payload) {
  return payload?.result || {}
}

export function getDecision(payload) {
  return getResult(payload).decision ?? getCompat(payload).decision ?? null
}

export function getQuantSignal(payload) {
  return getResult(payload).signals?.quant?.rating ?? getCompat(payload).quant_signal ?? null
}

export function getLlmSignal(payload) {
  return getResult(payload).signals?.llm?.rating ?? getCompat(payload).llm_signal ?? null
}

export function getConfidence(payload) {
  return getResult(payload).confidence ?? getCompat(payload).confidence ?? null
}

export function getDisplayDate(payload) {
  return payload?.date ?? getCompat(payload).analysis_date ?? null
}

export function getErrorMessage(payload) {
  const error = payload?.error
  if (!error) return null
  if (typeof error === 'string') return error
  return error.message || error.code || null
}

export function isCompletedLikeStatus(status) {
  return status === 'completed' || status === 'degraded_success'
}
