import { Check, X, Minus } from 'lucide-react';

interface AccuracyBadgeProps {
  correct: boolean | null;
  returnPercent: number;
  size?: 'small' | 'default';
}

export default function AccuracyBadge({
  correct,
  returnPercent,
  size = 'default',
}: AccuracyBadgeProps) {
  const isPositiveReturn = returnPercent >= 0;
  const sizeClasses = size === 'small' ? 'text-xs px-1.5 py-0.5 gap-1' : 'text-sm px-2 py-1 gap-1.5';
  const iconSize = size === 'small' ? 'w-3 h-3' : 'w-3.5 h-3.5';

  if (correct === null) {
    return (
      <span className={`inline-flex items-center rounded-full font-medium bg-gray-100 dark:bg-slate-700 text-gray-500 dark:text-gray-400 ${sizeClasses}`}>
        <Minus className={iconSize} />
        <span>Pending</span>
      </span>
    );
  }

  if (correct) {
    return (
      <span className={`inline-flex items-center rounded-full font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 ${sizeClasses}`}>
        <Check className={iconSize} />
        <span className={isPositiveReturn ? '' : 'text-green-600 dark:text-green-400'}>
          {isPositiveReturn ? '+' : ''}{returnPercent.toFixed(1)}%
        </span>
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center rounded-full font-medium bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 ${sizeClasses}`}>
      <X className={iconSize} />
      <span>
        {isPositiveReturn ? '+' : ''}{returnPercent.toFixed(1)}%
      </span>
    </span>
  );
}

interface AccuracyRateProps {
  rate: number;
  label?: string;
  size?: 'small' | 'default';
}

export function AccuracyRate({ rate, label = 'Accuracy', size = 'default' }: AccuracyRateProps) {
  const percentage = rate * 100;
  const isGood = percentage >= 60;
  const isModerate = percentage >= 40 && percentage < 60;

  const sizeClasses = size === 'small' ? 'text-xs' : 'text-sm';
  const colorClass = isGood
    ? 'text-green-600 dark:text-green-400'
    : isModerate
    ? 'text-amber-600 dark:text-amber-400'
    : 'text-red-600 dark:text-red-400';

  return (
    <div className={`flex items-center gap-1.5 ${sizeClasses}`}>
      <span className="text-gray-500 dark:text-gray-400">{label}:</span>
      <span className={`font-semibold ${colorClass}`}>{percentage.toFixed(0)}%</span>
    </div>
  );
}
