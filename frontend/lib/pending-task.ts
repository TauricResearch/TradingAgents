/**
 * Pending Task Tracker
 * Saves in-progress analysis tasks to localStorage so they can be recovered
 * if the user accidentally closes the page before completion
 */

const PENDING_TASK_KEY = 'tradingagents_pending_task';

export interface PendingTask {
  taskId: string;
  ticker: string;
  marketType: 'us' | 'twse' | 'tpex';
  analysisDate: string;
  startedAt: string;
}

/**
 * Save a pending task to localStorage
 */
export function savePendingTask(task: PendingTask): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(PENDING_TASK_KEY, JSON.stringify(task));
    console.log('📝 Saved pending task:', task.taskId);
  } catch (error) {
    console.error('Failed to save pending task:', error);
  }
}

/**
 * Get any pending task from localStorage
 */
export function getPendingTask(): PendingTask | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = localStorage.getItem(PENDING_TASK_KEY);
    if (!stored) return null;
    return JSON.parse(stored) as PendingTask;
  } catch (error) {
    console.error('Failed to get pending task:', error);
    return null;
  }
}

/**
 * Clear the pending task from localStorage (after successful save or completion)
 */
export function clearPendingTask(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(PENDING_TASK_KEY);
    console.log('✅ Cleared pending task');
  } catch (error) {
    console.error('Failed to clear pending task:', error);
  }
}

/**
 * Check if a pending task is still valid (not too old)
 * Tasks older than 24 hours are considered expired
 */
export function isPendingTaskValid(task: PendingTask): boolean {
  const started = new Date(task.startedAt).getTime();
  const now = Date.now();
  const maxAge = 24 * 60 * 60 * 1000; // 24 hours
  return now - started < maxAge;
}
