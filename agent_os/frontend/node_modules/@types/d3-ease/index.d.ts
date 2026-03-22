// Last module patch version validated against: 3.0.1

// --------------------------------------------------------------------------
// Easing Functions
// --------------------------------------------------------------------------

/**
 * Linear easing; the identity function; linear(t) returns t.
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeLinear(normalizedTime: number): number;

/**
 * Symmetric quadratic easing; scales quadIn for t in [0, 0.5] and quadOut for t in [0.5, 1]. Also equivalent to poly.exponent(2).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeQuad(normalizedTime: number): number;

/**
 * Quadratic easing; equivalent to polyIn.exponent(2).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeQuadIn(normalizedTime: number): number;

/**
 * Reverse quadratic easing; equivalent to 1 - quadIn(1 - t). Also equivalent to polyOut.exponent(2).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeQuadOut(normalizedTime: number): number;

/**
 * Symmetric quadratic easing; scales quadIn for t in [0, 0.5] and quadOut for t in [0.5, 1]. Also equivalent to poly.exponent(2).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeQuadInOut(normalizedTime: number): number;

/**
 * Symmetric cubic easing; scales cubicIn for t in [0, 0.5] and cubicOut for t in [0.5, 1]. Also equivalent to poly.exponent(3).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeCubic(normalizedTime: number): number;

/**
 * Cubic easing; equivalent to polyIn.exponent(3).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeCubicIn(normalizedTime: number): number;

/**
 * Reverse cubic easing; equivalent to 1 - cubicIn(1 - t). Also equivalent to polyOut.exponent(3).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeCubicOut(normalizedTime: number): number;

/**
 * Symmetric cubic easing; scales cubicIn for t in [0, 0.5] and cubicOut for t in [0.5, 1]. Also equivalent to poly.exponent(3).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeCubicInOut(normalizedTime: number): number;

/**
 * Polynomial easing function factory
 */
export interface PolynomialEasingFactory {
    /**
     * Calculate eased time.
     * @param normalizedTime Normalized time typically in the range [0, 1]
     */
    (normalizedTime: number): number;
    /**
     * Returns a new polynomial easing with the specified exponent e.
     * If the exponent is not specified, it defaults to 3, equivalent to cubic.
     *
     * @param e Exponent for polynomial easing.
     */
    exponent(e: number): PolynomialEasingFactory;
}

/**
 * Symmetric polynomial easing/easing factory; scales polyIn for t in [0, 0.5] and polyOut for t in [0.5, 1].
 * If the exponent is not specified, it defaults to 3, equivalent to cubic.
 */
export const easePoly: PolynomialEasingFactory;
/**
 * Polynomial easing/easing factory; raises t to the specified exponent.
 * If the exponent is not specified, it defaults to 3, equivalent to cubicIn.
 */
export const easePolyIn: PolynomialEasingFactory;

/**
 * Reverse polynomial easing/easing factory; equivalent to 1 - polyIn(1 - t).
 * If the exponent is not specified, it defaults to 3, equivalent to cubicOut.
 */
export const easePolyOut: PolynomialEasingFactory;

/**
 * Symmetric polynomial easing/easing factory; scales polyIn for t in [0, 0.5] and polyOut for t in [0.5, 1].
 * If the exponent is not specified, it defaults to 3, equivalent to cubic.
 */
export const easePolyInOut: PolynomialEasingFactory;

/**
 * Symmetric sinusoidal easing; scales sinIn for t in [0, 0.5] and sinOut for t in [0.5, 1].
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeSin(normalizedTime: number): number;

/**
 * Sinusoidal easing; returns sin(t).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeSinIn(normalizedTime: number): number;

/**
 * Reverse sinusoidal easing; equivalent to 1 - sinIn(1 - t).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeSinOut(normalizedTime: number): number;

/**
 * Symmetric sinusoidal easing; scales sinIn for t in [0, 0.5] and sinOut for t in [0.5, 1].
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeSinInOut(normalizedTime: number): number;

/**
 * Symmetric exponential easing; scales expIn for t in [0, 0.5] and expOut for t in [0.5, 1].
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeExp(normalizedTime: number): number;

/**
 * Exponential easing; raises 2 to the exponent 10 * (t - 1).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeExpIn(normalizedTime: number): number;

/**
 * Reverse exponential easing; equivalent to 1 - expIn(1 - t).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeExpOut(normalizedTime: number): number;

/**
 * Symmetric exponential easing; scales expIn for t in [0, 0.5] and expOut for t in [0.5, 1].
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeExpInOut(normalizedTime: number): number;

/**
 * Symmetric circular easing; scales circleIn for t in [0, 0.5] and circleOut for t in [0.5, 1].
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeCircle(normalizedTime: number): number;

/**
 * Circular easing.
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeCircleIn(normalizedTime: number): number;

/**
 * Reverse circular easing; equivalent to 1 - circleIn(1 - t).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeCircleOut(normalizedTime: number): number;

/**
 * Symmetric circular easing; scales circleIn for t in [0, 0.5] and circleOut for t in [0.5, 1].
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeCircleInOut(normalizedTime: number): number;

/**
 * Reverse bounce easing; equivalent to 1 - bounceIn(1 - t).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeBounce(normalizedTime: number): number;

/**
 * Bounce easing, like a rubber ball.
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeBounceIn(normalizedTime: number): number;

/**
 * Reverse bounce easing; equivalent to 1 - bounceIn(1 - t).
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeBounceOut(normalizedTime: number): number;

/**
 * Symmetric bounce easing; scales bounceIn for t in [0, 0.5] and bounceOut for t in [0.5, 1].
 *
 * @param normalizedTime Normalized time typically in the range [0, 1]
 */
export function easeBounceInOut(normalizedTime: number): number;

/**
 * Anticipatory easing function factory
 */
export interface BackEasingFactory {
    /**
     * Calculate eased time.
     * @param normalizedTime Normalized time typically in the range [0, 1]
     */
    (normalizedTime: number): number;
    /**
     * Returns a new back easing with the specified overshoot s.
     * The degree of overshoot is configurable; if not specified, it defaults to 1.70158.
     *
     * @param s Overshoot parameter
     */
    overshoot(s: number): BackEasingFactory;
}

/**
 * Symmetric anticipatory easing; scales backIn for t in [0, 0.5] and backOut for t in [0.5, 1].
 * The degree of overshoot is configurable; it not specified, it defaults to 1.70158.
 */
export const easeBack: BackEasingFactory;

/**
 * Anticipatory easing, like a dancer bending their knees before jumping off the floor.
 * The degree of overshoot is configurable; it not specified, it defaults to 1.70158.
 */
export const easeBackIn: BackEasingFactory;

/**
 * Reverse anticipatory easing; equivalent to 1 - backIn(1 - t).
 * The degree of overshoot is configurable; it not specified, it defaults to 1.70158.
 */
export const easeBackOut: BackEasingFactory;

/**
 * Symmetric anticipatory easing; scales backIn for t in [0, 0.5] and backOut for t in [0.5, 1].
 * The degree of overshoot is configurable; it not specified, it defaults to 1.70158.
 */
export const easeBackInOut: BackEasingFactory;

/**
 * Elastic easing function factory
 */
export interface ElasticEasingFactory {
    /**
     * Calculate eased time.
     * @param normalizedTime Normalized time typically in the range [0, 1]
     */
    (normalizedTime: number): number;
    /**
     * Returns a new elastic easing with the specified amplitude a.
     * Defaults to 1,if not specified.
     *
     * @param a Amplitude for elastic easing.
     */
    amplitude(a: number): ElasticEasingFactory;
    /**
     * Returns a new elastic easing with the specified amplitude a.
     * Defaults to 0.3,if not specified.
     *
     * @param p Period for elastic easing.
     */
    period(p: number): ElasticEasingFactory;
}

/**
 * Reverse elastic easing; equivalent to 1 - elasticIn(1 - t).
 * The amplitude and period of the oscillation are configurable;
 * if not specified, they default to 1 and 0.3, respectively.
 */
export const easeElastic: ElasticEasingFactory;

/**
 * Elastic easing, like a rubber band.
 * The amplitude and period of the oscillation are configurable;
 * if not specified, they default to 1 and 0.3, respectively.
 */
export const easeElasticIn: ElasticEasingFactory;

/**
 * Reverse elastic easing; equivalent to 1 - elasticIn(1 - t).
 * The amplitude and period of the oscillation are configurable;
 * if not specified, they default to 1 and 0.3, respectively.
 */
export const easeElasticOut: ElasticEasingFactory;

/**
 * Symmetric elastic easing; scales elasticIn for t in [0, 0.5] and elasticOut for t in [0.5, 1].
 * The amplitude and period of the oscillation are configurable;
 * if not specified, they default to 1 and 0.3, respectively.
 */
export const easeElasticInOut: ElasticEasingFactory;
