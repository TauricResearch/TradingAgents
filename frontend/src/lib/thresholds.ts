/** Statistical honesty bars (trader review P0.6): numbers below these
 * sample sizes render as "accruing", never as statistics. The product's
 * credibility rests on refusing to dress noise as insight. */

/** Minimum scored outcomes before an agent's hit rate / calibration gap
 * counts as a statistic. */
export const MIN_SCORED = 20;

/** Minimum similarity before a retrieved past trade is presented as a
 * historical analog (the review saw a "12% similar" analog headlining). */
export const MIN_ANALOG_SIMILARITY = 0.5;
