// Last module patch version validated against: 4.0.2

import { CountableTimeInterval, TimeInterval } from "d3-time";

// -------------------------------------------------------------------------------
// Shared Types and Interfaces
// -------------------------------------------------------------------------------

/**
 * An Interpolator factory returns an interpolator function.
 *
 * The first generic corresponds to the data type of the interpolation boundaries.
 * The second generic corresponds to the data type of the return type of the interpolator.
 */
export interface InterpolatorFactory<T, U> {
    /**
     * Construct a new interpolator function, based on the provided interpolation boundaries.
     *
     * @param a Start boundary of the interpolation interval.
     * @param b End boundary of the interpolation interval.
     */
    (a: T, b: T): (t: number) => U;
}

export type NumberValue = number | { valueOf(): number };

export type UnknownReturnType<Unknown, DefaultUnknown> = [Unknown] extends [never] ? DefaultUnknown : Unknown;

/**
 * A helper interface for a continuous scale defined over a numeric domain.
 */
export interface ScaleContinuousNumeric<Range, Output, Unknown = never> {
    /**
     * Given a value from the domain, returns the corresponding value from the range, subject to interpolation, if any.
     *
     * If the given value is outside the domain, and clamping is not enabled, the mapping may be extrapolated such that the returned value is outside the range.
     *
     * Note: The interpolation function applied by the scale may change the output type from the range type as part of the interpolation.
     *
     * @param value A numeric value from the domain.
     */
    (value: NumberValue): Output | Unknown;

    /**
     * Given a value from the range, returns the corresponding value from the domain. Inversion is useful for interaction,
     * say to determine the data value corresponding to the position of the mouse.
     *
     * If the given value is outside the range, and clamping is not enabled, the mapping may be extrapolated such that the returned value is outside the domain.
     *
     * IMPORTANT: This method is only supported if the range is numeric. If the range is not numeric, returns NaN.
     *
     * For a valid value y in the range, continuous(continuous.invert(y)) approximately equals y;
     * similarly, for a valid value x in the domain, continuous.invert(continuous(x)) approximately equals x.
     * The scale and its inverse may not be exact due to the limitations of floating point precision.
     *
     * @param value A numeric value from the range.
     */
    invert(value: NumberValue): number;

    /**
     * Returns a copy of the scale’s current domain.
     */
    domain(): number[];
    /**
     * Sets the scale’s domain to the specified array of numbers. The array must contain two or more elements.
     * If the elements in the given array are not numbers, they will be coerced to numbers
     *
     * Although continuous scales typically have two values each in their domain and range, specifying more than two values produces a piecewise scale.
     *
     * Internally, a piecewise scale performs a binary search for the range interpolator corresponding to the given domain value.
     * Thus, the domain must be in ascending or descending order. If the domain and range have different lengths N and M, only the first min(N,M) elements in each are observed.
     *
     * @param domain Array of numeric domain values.
     */
    domain(domain: Iterable<NumberValue>): this;

    /**
     * Returns a copy of the scale’s current range.
     */
    range(): Range[];
    /**
     * Sets the scale’s range to the specified array of values.
     *
     * The array must contain two or more elements. Unlike the domain, elements in the given array need not be numbers;
     * any value that is supported by the underlying interpolator will work, though note that numeric ranges are required for invert.
     *
     * @param range Array of range values.
     */
    range(range: Iterable<Range>): this;

    /**
     * Sets the scale’s range to the specified array of values while also setting the scale’s interpolator to interpolateRound.
     *
     * The rounding interpolator is sometimes useful for avoiding antialiasing artifacts,
     * though also consider the shape-rendering “crispEdges” styles. Note that this interpolator can only be used with numeric ranges.
     *
     * The array must contain two or more elements. Unlike the domain, elements in the given array need not be numbers;
     * any value that is supported by the underlying interpolator will work, though note that numeric ranges are required for invert.
     *
     * @param range Array of range values.
     */
    rangeRound(range: Iterable<NumberValue>): this;

    /**
     * Returns whether or not the scale currently clamps values to within the range.
     */
    clamp(): boolean;
    /**
     * Enables or disables clamping, respectively. If clamping is disabled and the scale is passed a value outside the domain,
     * the scale may return a value outside the range through extrapolation.
     *
     * If clamping is enabled, the return value of the scale is always within the scale’s range. Clamping similarly applies to the "invert" method.
     *
     * @param clamp A flag to enable (true) or disable (false) clamping.
     */
    clamp(clamp: boolean): this;

    /**
     * Returns approximately count representative values from the scale’s domain.
     *
     * If count is not specified, it defaults to 10.
     *
     * The returned tick values are uniformly spaced, have human-readable values (such as multiples of powers of 10),
     * and are guaranteed to be within the extent of the domain. Ticks are often used to display reference lines, or tick marks, in conjunction with the visualized data.
     * The specified count is only a hint; the scale may return more or fewer values depending on the domain. See also d3-array’s ticks.
     *
     * @param count Optional approximate number of ticks to be returned. If count is not specified, it defaults to 10.
     */
    ticks(count?: number): number[];

    /**
     * Returns a number format function suitable for displaying a tick value, automatically computing the appropriate precision based on the fixed interval between tick values.
     * The specified count should have the same value as the count that is used to generate the tick values.
     *
     * @param count Approximate number of ticks to be used when calculating precision for the number format function.
     * @param specifier An optional valid format specifier string which allows a custom format where the precision of the format is automatically set by the scale as appropriate for the tick interval.
     * If specifier uses the format type "s", the scale will return a SI-prefix format based on the largest value in the domain.
     * If the specifier already specifies a precision, this method is equivalent to locale.format.
     */
    tickFormat(count?: number, specifier?: string): (d: NumberValue) => string;

    /**
     * Extends the domain so that it starts and ends on nice round values.
     * This method typically modifies the scale’s domain, and may only extend the bounds to the nearest round value.
     * An optional tick count argument allows greater control over the step size used to extend the bounds,
     * guaranteeing that the returned ticks will exactly cover the domain.
     * Nicing is useful if the domain is computed from data, say using extent, and may be irregular.
     * For example, for a domain of [0.201479…, 0.996679…], a nice domain might be [0.2, 1.0].
     * If the domain has more than two values, nicing the domain only affects the first and last value.
     *
     * Nicing a scale only modifies the current domain; it does not automatically nice domains that are subsequently set using continuous.domain.
     * You must re-nice the scale after setting the new domain, if desired.
     *
     * @param count An optional number of ticks expected to be used.
     */
    nice(count?: number): this;

    /**
     * Returns an exact copy of this scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;
}

/**
 * Returns a number format function suitable for displaying a tick value,
 * automatically computing the appropriate precision based on the fixed interval between tick values, as determined by d3.tickStep.
 *
 * @param start Start
 * @param stop Stop
 * @param count Approximate number of ticks to be used when calculating precision for the number format function.
 * @param specifier An optional specifier allows a custom format where the precision of the format is automatically set by the scale as appropriate for the tick interval.
 * If specifier uses the format type s, the scale will return a SI-prefix format based on the larger absolute value of start and stop.
 * If the specifier already specifies a precision, this method is equivalent to locale.format.
 */
export function tickFormat(start: number, stop: number, count: number, specifier?: string): (d: NumberValue) => string;

// -------------------------------------------------------------------------------
// Linear Scale Factory
// -------------------------------------------------------------------------------

/**
 * A linear continuous scale defined over a numeric domain.
 *
 * Continuous scales map a continuous, quantitative input domain to a continuous output range.
 * Each range value y can be expressed as a function of the domain value x: y = mx + b.
 *
 * If the range is also numeric, the mapping may be inverted.
 *
 * Note that the data types of the range and output of the scale must be compatible with the interpolator applied by the scale.
 *
 * The first generic corresponds to the data type of the range elements.
 *
 * The second generic corresponds to the data type of the output elements generated by the scale.
 *
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 */
export interface ScaleLinear<Range, Output, Unknown = never> extends ScaleContinuousNumeric<Range, Output, Unknown> {
    /**
     * Returns the scale’s current interpolator factory, which defaults to interpolate.
     */
    interpolate(): InterpolatorFactory<any, any>;

    /**
     * Sets the scale’s range interpolator factory. This interpolator factory is used to create interpolators for each adjacent pair of values from the range;
     * these interpolators then map a normalized domain parameter t in [0, 1] to the corresponding value in the range.
     *
     * Note: the default interpolator may reuse return values. For example, if the range values are objects, then the value interpolator always returns the same object, modifying it in-place.
     * If the scale is used to set an attribute or style, this is typically acceptable (and desirable for performance);
     * however, if you need to store the scale’s return value, you must specify your own interpolator or make a copy as appropriate.
     *
     * As part of the interpolation process the interpolated value from the range may be converted to a corresponding output value.
     *
     * @param interpolate An interpolation factory. The generics for Range and Output of the scale must correspond to the interpolation factory applied to the scale.
     */
    interpolate(interpolate: InterpolatorFactory<Range, Output>): this;
    /**
     * Sets the scale’s range interpolator factory. This interpolator factory is used to create interpolators for each adjacent pair of values from the range;
     * these interpolators then map a normalized domain parameter t in [0, 1] to the corresponding value in the range.
     *
     * Note: the default interpolator may reuse return values. For example, if the range values are objects, then the value interpolator always returns the same object, modifying it in-place.
     * If the scale is used to set an attribute or style, this is typically acceptable (and desirable for performance);
     * however, if you need to store the scale’s return value, you must specify your own interpolator or make a copy as appropriate.
     *
     * As part of the interpolation process the interpolated value from the range may be converted to a corresponding output value.
     *
     * The generic "NewOutput" can be used to change the scale to have a different output element type corresponding to the new interpolation factory.
     *
     * @param interpolate An interpolation factory. The generics for Range and Output of the scale must correspond to the interpolation factory applied to the scale.
     */
    interpolate<NewOutput>(interpolate: InterpolatorFactory<Range, NewOutput>): ScaleLinear<Range, NewOutput, Unknown>;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleLinear<Range, Output, NewUnknown>;
}

/**
 * Constructs a new continuous scale with the specified range, the default interpolator and clamping disabled.
 * The domain defaults to [0, 1].
 * If range is not specified, it defaults to [0, 1].
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleLinear<Range = number, Output = Range, Unknown = never>(
    range?: Iterable<Range>,
): ScaleLinear<Range, Output, Unknown>;
/**
 * Constructs a new continuous scale with the specified domain and range, the default interpolator and clamping disabled.
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param domain Array of numeric domain values.
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleLinear<Range, Output = Range, Unknown = never>(
    domain: Iterable<NumberValue>,
    range: Iterable<Range>,
): ScaleLinear<Range, Output, Unknown>;

// -------------------------------------------------------------------------------
// Power Scale Factories
// -------------------------------------------------------------------------------

/**
 * A continuous power scale defined over a numeric domain.
 *
 * Continuous scales map a continuous, quantitative input domain to a continuous output range.
 *
 * Each range value y can be expressed as a function of the domain value x: y = mx^k + b, where k is the exponent value.
 * Power scales also support negative domain values, in which case the input value and the resulting output value are multiplied by -1.
 *
 * If the range is also numeric, the mapping may be inverted.
 *
 * Note that the data types of the range and output of the scale must be compatible with the interpolator applied by the scale.
 *
 * The first generic corresponds to the data type of the range elements.
 *
 * The second generic corresponds to the data type of the output elements generated by the scale.
 *
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 */
export interface ScalePower<Range, Output, Unknown = never> extends ScaleContinuousNumeric<Range, Output, Unknown> {
    /**
     * Returns the scale’s current interpolator factory, which defaults to interpolate.
     */
    interpolate(): InterpolatorFactory<any, any>;

    /**
     * Sets the scale’s range interpolator factory. This interpolator factory is used to create interpolators for each adjacent pair of values from the range;
     * these interpolators then map a normalized domain parameter t in [0, 1] to the corresponding value in the range.
     *
     * Note: the default interpolator may reuse return values. For example, if the range values are objects, then the value interpolator always returns the same object, modifying it in-place.
     * If the scale is used to set an attribute or style, this is typically acceptable (and desirable for performance);
     * however, if you need to store the scale’s return value, you must specify your own interpolator or make a copy as appropriate.
     *
     * As part of the interpolation process the interpolated value from the range may be converted to a corresponding output value.
     *
     * @param interpolate An interpolation factory. The generics for Range and Output of the scale must correspond to the interpolation factory applied to the scale.
     */
    interpolate(interpolate: InterpolatorFactory<Range, Output>): this;
    /**
     * Sets the scale’s range interpolator factory. This interpolator factory is used to create interpolators for each adjacent pair of values from the range;
     * these interpolators then map a normalized domain parameter t in [0, 1] to the corresponding value in the range.
     *
     * Note: the default interpolator may reuse return values. For example, if the range values are objects, then the value interpolator always returns the same object, modifying it in-place.
     * If the scale is used to set an attribute or style, this is typically acceptable (and desirable for performance);
     * however, if you need to store the scale’s return value, you must specify your own interpolator or make a copy as appropriate.
     *
     * As part of the interpolation process the interpolated value from the range may be converted to a corresponding output value.
     *
     * The generic "NewOutput" can be used to change the scale to have a different output element type corresponding to the new interpolation factory.
     *
     * @param interpolate An interpolation factory. The generics for Range and Output of the scale must correspond to the interpolation factory applied to the scale.
     */
    interpolate<NewOutput>(interpolate: InterpolatorFactory<Range, NewOutput>): ScalePower<Range, NewOutput, Unknown>;

    /**
     * If exponent is not specified, returns the current exponent, which defaults to 1.
     * (Note that this is effectively a linear scale until you set a different exponent.)
     */
    exponent(): number;
    /**
     * Sets the current exponent to the given numeric value.
     * (Note that this is effectively a linear scale until you set a different exponent.)
     */
    exponent(exponent: number): this;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScalePower<Range, Output, NewUnknown>;
}

/**
 * Constructs a new continuous scale with the specified range, the exponent 1, the default interpolator and clamping disabled.
 * The domain defaults to [0, 1].
 * If range is not specified, it defaults to [0, 1].
 * (Note that this is effectively a linear scale until you set a different exponent.)
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scalePow<Range = number, Output = Range, Unknown = never>(
    range?: Iterable<Range>,
): ScalePower<Range, Output, Unknown>;
/**
 * Constructs a new continuous scale with the specified domain and range, the exponent 1, the default interpolator and clamping disabled.
 * (Note that this is effectively a linear scale until you set a different exponent.)
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param domain Array of numeric domain values.
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scalePow<Range, Output = Range, Unknown = never>(
    domain: Iterable<NumberValue>,
    range: Iterable<Range>,
): ScalePower<Range, Output, Unknown>;

/**
 * Constructs a new continuous power scale with the specified range, the exponent 0.5, the default interpolator and clamping disabled.
 * The domain defaults to [0, 1].
 * If range is not specified, it defaults to [0, 1].
 * This is a convenience method equivalent to d3.scalePow().exponent(0.5).
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSqrt<Range = number, Output = Range, Unknown = never>(
    range?: Iterable<Range>,
): ScalePower<Range, Output, Unknown>;
/**
 * Constructs a new continuous power scale with the specified domain and range, the exponent 0.5, the default interpolator and clamping disabled.
 * This is a convenience method equivalent to d3.scalePow().exponent(0.5).
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param domain Array of numeric domain values.
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSqrt<Range, Output = Range, Unknown = never>(
    domain: Iterable<NumberValue>,
    range: Iterable<Range>,
): ScalePower<Range, Output, Unknown>;

// -------------------------------------------------------------------------------
// Logarithmic Scale Factory
// -------------------------------------------------------------------------------

/**
 * A continuous logarithmic scale defined over a numeric domain.
 *
 * Continuous scales map a continuous, quantitative input domain to a continuous output range.
 *
 * The mapping to the range value y can be expressed as a function of the domain value x: y = m log(x) + b.
 *
 * As log(0) = -∞, a log scale domain must be strictly-positive or strictly-negative; the domain must not include or cross zero.
 * A log scale with a positive domain has a well-defined behavior for positive values, and a log scale with a negative domain has a well-defined behavior for negative values.
 * (For a negative domain, input and output values are implicitly multiplied by -1.)
 * The behavior of the scale is undefined if you pass a negative value to a log scale with a positive domain or vice versa.
 *
 * If the range is also numeric, the mapping may be inverted.
 *
 * Note that the data types of the range and output of the scale must be compatible with the interpolator applied by the scale.
 *
 * The first generic corresponds to the data type of the range elements.
 *
 * The second generic corresponds to the data type of the output elements generated by the scale.
 *
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 */
export interface ScaleLogarithmic<Range, Output, Unknown = never>
    extends ScaleContinuousNumeric<Range, Output, Unknown>
{
    /**
     * Returns a copy of the scale’s current domain.
     */
    domain(): number[];
    /**
     * Sets the scale’s domain to the specified array of numbers. The array must contain two or more elements.
     * If the elements in the given array are not numbers, they will be coerced to numbers
     *
     * As log(0) = -∞, a log scale domain must be strictly-positive or strictly-negative; the domain must not include or cross zero.
     * A log scale with a positive domain has a well-defined behavior for positive values, and a log scale with a negative domain has a well-defined behavior for negative values.
     * (For a negative domain, input and output values are implicitly multiplied by -1.)
     * The behavior of the scale is undefined if you pass a negative value to a log scale with a positive domain or vice versa.
     *
     * Although continuous scales typically have two values each in their domain and range, specifying more than two values produces a piecewise scale.
     *
     * Internally, a piecewise scale performs a binary search for the range interpolator corresponding to the given domain value.
     * Thus, the domain must be in ascending or descending order. If the domain and range have different lengths N and M, only the first min(N,M) elements in each are observed.
     *
     * @param domain Array of numeric domain values.
     */
    domain(domain: Iterable<NumberValue>): this;

    /**
     * Returns the scale’s current interpolator factory, which defaults to interpolate.
     */
    interpolate(): InterpolatorFactory<any, any>;

    /**
     * Sets the scale’s range interpolator factory. This interpolator factory is used to create interpolators for each adjacent pair of values from the range;
     * these interpolators then map a normalized domain parameter t in [0, 1] to the corresponding value in the range.
     *
     * Note: the default interpolator may reuse return values. For example, if the range values are objects, then the value interpolator always returns the same object, modifying it in-place.
     * If the scale is used to set an attribute or style, this is typically acceptable (and desirable for performance);
     * however, if you need to store the scale’s return value, you must specify your own interpolator or make a copy as appropriate.
     *
     * As part of the interpolation process the interpolated value from the range may be converted to a corresponding output value.
     *
     * @param interpolate An interpolation factory. The generics for Range and Output of the scale must correspond to the interpolation factory applied to the scale.
     */
    interpolate(interpolate: InterpolatorFactory<Range, Output>): this;
    /**
     * Sets the scale’s range interpolator factory. This interpolator factory is used to create interpolators for each adjacent pair of values from the range;
     * these interpolators then map a normalized domain parameter t in [0, 1] to the corresponding value in the range.
     *
     * Note: the default interpolator may reuse return values. For example, if the range values are objects, then the value interpolator always returns the same object, modifying it in-place.
     * If the scale is used to set an attribute or style, this is typically acceptable (and desirable for performance);
     * however, if you need to store the scale’s return value, you must specify your own interpolator or make a copy as appropriate.
     *
     * As part of the interpolation process the interpolated value from the range may be converted to a corresponding output value.
     *
     * The generic "NewOutput" can be used to change the scale to have a different output element type corresponding to the new interpolation factory.
     *
     * @param interpolate An interpolation factory. The generics for Range and Output of the scale must correspond to the interpolation factory applied to the scale.
     */
    interpolate<NewOutput>(
        interpolate: InterpolatorFactory<Range, NewOutput>,
    ): ScaleLogarithmic<Range, NewOutput, Unknown>;

    /**
     * Returns approximately count representative values from the scale’s domain.
     *
     * If count is not specified, it defaults to 10.
     *
     * If the base is an integer, the returned ticks are uniformly spaced within each integer power of base; otherwise, one tick per power of base is returned.
     * The returned ticks are guaranteed to be within the extent of the domain. If the orders of magnitude in the domain is greater than count, then at most one tick per power is returned.
     * Otherwise, the tick values are unfiltered, but note that you can use log.tickFormat to filter the display of tick labels.
     *
     * @param count Optional approximate number of ticks to be returned. If count is not specified, it defaults to 10.
     */
    ticks(count?: number): number[];

    /**
     * Returns a number format function suitable for displaying a tick value, automatically computing the appropriate precision based on the fixed interval between tick values.
     *
     * The specified count typically has the same value as the count that is used to generate the tick values.
     * If there are too many ticks, the formatter may return the empty string for some of the tick labels;
     * however, note that the ticks are still shown.
     * To disable filtering, specify a count of Infinity. When specifying a count, you may also provide a format specifier or format function.
     * For example, to get a tick formatter that will display 20 ticks of a currency, say log.tickFormat(20, "$,f").
     * If the specifier does not have a defined precision, the precision will be set automatically by the scale, returning the appropriate format.
     * This provides a convenient way of specifying a format whose precision will be automatically set by the scale.
     *
     * @param count Approximate number of ticks to be used when calculating precision for the number format function.
     * @param specifier An optional valid format specifier string which allows a custom format where the precision of the format is automatically set by the scale as appropriate for the tick interval.
     * For example, to get a tick formatter that will display 20 ticks of a currency, say log.tickFormat(20, "$,f").
     * If the specifier does not have a defined precision, the precision will be set automatically by the scale, returning the appropriate format.
     * This provides a convenient way of specifying a format whose precision will be automatically set by the scale.
     */
    tickFormat(count?: number, specifier?: string): (d: NumberValue) => string;

    /**
     * Extends the domain to integer powers of base. For example, for a domain of [0.201479…, 0.996679…], and base 10, the nice domain is [0.1, 1].
     * If the domain has more than two values, nicing the domain only affects the first and last value.
     *
     * Nicing a scale only modifies the current domain; it does not automatically nice domains that are subsequently set using continuous.domain.
     * You must re-nice the scale after setting the new domain, if desired.
     */
    nice(): this;

    /**
     * Returns the current base, which defaults to 10.
     */
    base(): number;
    /**
     * Sets the base for this logarithmic scale to the specified value.
     */
    base(base: number): this;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleLogarithmic<Range, Output, NewUnknown>;
}

/**
 * Constructs a new continuous scale with the specified range, the base 10, the default interpolator and clamping disabled.
 * The domain defaults to [1, 10].
 * If range is not specified, it defaults to [0, 1].
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleLog<Range = number, Output = Range, Unknown = never>(
    range?: Iterable<Range>,
): ScaleLogarithmic<Range, Output, Unknown>;
/**
 * Constructs a new continuous scale with the specified domain and range, the base 10, the default interpolator and clamping disabled.
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param domain Array of numeric domain values.
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleLog<Range, Output = Range, Unknown = never>(
    domain: Iterable<NumberValue>,
    range: Iterable<Range>,
): ScaleLogarithmic<Range, Output, Unknown>;

// -------------------------------------------------------------------------------
// Symlog Scale Factory
// -------------------------------------------------------------------------------

/**
 * A bi-symmetric log transformation for wide-range data by Webber scale defined over a numeric domain.
 *
 * Continuous scales map a continuous, quantitative input domain to a continuous output range.
 *
 * See “A bi-symmetric log transformation for wide-range data” by Webber for more
 *
 * If the range is also numeric, the mapping may be inverted.
 *
 * Note that the data types of the range and output of the scale must be compatible with the interpolator applied by the scale.
 *
 * The first generic corresponds to the data type of the range elements.
 *
 * The second generic corresponds to the data type of the output elements generated by the scale.
 *
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 */
export interface ScaleSymLog<Range, Output, Unknown = never> extends ScaleContinuousNumeric<Range, Output, Unknown> {
    /**
     * Returns a number format function suitable for displaying a tick value, automatically computing the appropriate precision based on the fixed interval between tick values.
     *
     * The specified count typically has the same value as the count that is used to generate the tick values.
     * If there are too many ticks, the formatter may return the empty string for some of the tick labels;
     * however, note that the ticks are still shown.
     * To disable filtering, specify a count of Infinity. When specifying a count, you may also provide a format specifier or format function.
     * For example, to get a tick formatter that will display 20 ticks of a currency, say log.tickFormat(20, "$,f").
     * If the specifier does not have a defined precision, the precision will be set automatically by the scale, returning the appropriate format.
     * This provides a convenient way of specifying a format whose precision will be automatically set by the scale.
     *
     * @param count Approximate number of ticks to be used when calculating precision for the number format function.
     * @param specifier An optional valid format specifier string which allows a custom format where the precision of the format is automatically set by the scale as appropriate for the tick interval.
     * For example, to get a tick formatter that will display 20 ticks of a currency, say log.tickFormat(20, "$,f").
     * If the specifier does not have a defined precision, the precision will be set automatically by the scale, returning the appropriate format.
     * This provides a convenient way of specifying a format whose precision will be automatically set by the scale.
     */
    tickFormat(count?: number, specifier?: string): (d: NumberValue) => string;
    /**
     * Returns the current constant, which defaults to 1.
     */
    constant(): number;
    /**
     * Sets the symlog constant to the specified number and returns this scale;
     * otherwise returns the current value of the symlog constant, which defaults to 1. See “A bi-symmetric log transformation for wide-range data” by Webber for more.
     */
    constant(constant: number): this;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleSymLog<Range, Output, NewUnknown>;
}

/**
 * Constructs a new continuous scale with the specified range, the constant 1, the default interpolator and clamping disabled.
 * The domain defaults to [0, 1].
 * If range is not specified, it defaults to [0, 1].
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSymlog<Range = number, Output = Range, Unknown = never>(
    range?: Iterable<Range>,
): ScaleSymLog<Range, Output, Unknown>;
/**
 * Constructs a new continuous scale with the specified domain and range, the constant 1, the default interpolator and clamping disabled.
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param domain Array of numeric domain values.
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSymlog<Range, Output = Range, Unknown = never>(
    domain: Iterable<NumberValue>,
    range: Iterable<Range>,
): ScaleSymLog<Range, Output, Unknown>;

// -------------------------------------------------------------------------------
// Identity Scale Factory
// -------------------------------------------------------------------------------

/**
 * Identity scales are a special case of linear scales where the domain and range are identical; the scale and its invert method are thus the identity function.
 * These scales are occasionally useful when working with pixel coordinates, say in conjunction with an axis.
 *
 * The generic corresponds to the data type of the unknown value.
 */
export interface ScaleIdentity<Unknown = never> {
    /**
     * Given a value from the domain, returns the corresponding value from the range, subject to interpolation, if any.
     *
     * If the given value is outside the domain, and clamping is not enabled, the mapping may be extrapolated such that the returned value is outside the range.
     *
     * Note: The interpolation function applied by the scale may change the output type from the range type as part of the interpolation.
     *
     * @param value A numeric value from the domain.
     */
    (value: NumberValue): number | Unknown;

    /**
     * Given a value from the range, returns the corresponding value from the domain. Inversion is useful for interaction,
     * say to determine the data value corresponding to the position of the mouse.
     *
     * If the given value is outside the range, and clamping is not enabled, the mapping may be extrapolated such that the returned value is outside the domain.
     *
     * IMPORTANT: This method is only supported if the range is numeric. If the range is not numeric, returns NaN.
     *
     * For a valid value y in the range, continuous(continuous.invert(y)) approximately equals y;
     * similarly, for a valid value x in the domain, continuous.invert(continuous(x)) approximately equals x.
     * The scale and its inverse may not be exact due to the limitations of floating point precision.
     *
     * @param value A numeric value from the range.
     */
    invert(value: NumberValue): number;

    /**
     * Returns a copy of the scale’s current domain.
     */
    domain(): number[];
    /**
     * Sets the scale’s domain to the specified array of numbers. The array must contain two or more elements.
     * If the elements in the given array are not numbers, they will be coerced to numbers
     *
     * Although continuous scales typically have two values each in their domain and range, specifying more than two values produces a piecewise scale.
     *
     * Internally, a piecewise scale performs a binary search for the range interpolator corresponding to the given domain value.
     * Thus, the domain must be in ascending or descending order. If the domain and range have different lengths N and M, only the first min(N,M) elements in each are observed.
     *
     * @param domain Array of numeric domain values.
     */
    domain(domain: Iterable<NumberValue>): this;

    /**
     * Returns a copy of the scale’s current range.
     */
    range(): number[];
    /**
     * Sets the scale’s range to the specified array of values.
     *
     * The array must contain two or more elements. Unlike the domain, elements in the given array need not be numbers;
     * any value that is supported by the underlying interpolator will work, though note that numeric ranges are required for invert.
     *
     * @param range Array of range values.
     */
    range(range: Iterable<NumberValue>): this;

    /**
     * Returns approximately count representative values from the scale’s domain.
     *
     * If count is not specified, it defaults to 10.
     *
     * The returned tick values are uniformly spaced, have human-readable values (such as multiples of powers of 10),
     * and are guaranteed to be within the extent of the domain. Ticks are often used to display reference lines, or tick marks, in conjunction with the visualized data.
     * The specified count is only a hint; the scale may return more or fewer values depending on the domain. See also d3-array’s ticks.
     *
     * @param count Optional approximate number of ticks to be returned. If count is not specified, it defaults to 10.
     */
    ticks(count?: number): number[];

    /**
     * Returns a number format function suitable for displaying a tick value, automatically computing the appropriate precision based on the fixed interval between tick values.
     * The specified count should have the same value as the count that is used to generate the tick values.
     *
     * @param count Approximate number of ticks to be used when calculating precision for the number format function.
     * @param specifier An optional valid format specifier string which allows a custom format where the precision of the format is automatically set by the scale as appropriate for the tick interval.
     * If specifier uses the format type "s", the scale will return a SI-prefix format based on the largest value in the domain.
     * If the specifier already specifies a precision, this method is equivalent to locale.format.
     */
    tickFormat(count?: number, specifier?: string): (d: NumberValue) => string;

    /**
     * Extends the domain so that it starts and ends on nice round values.
     * This method typically modifies the scale’s domain, and may only extend the bounds to the nearest round value.
     * An optional tick count argument allows greater control over the step size used to extend the bounds,
     * guaranteeing that the returned ticks will exactly cover the domain.
     * Nicing is useful if the domain is computed from data, say using extent, and may be irregular.
     * For example, for a domain of [0.201479…, 0.996679…], a nice domain might be [0.2, 1.0].
     * If the domain has more than two values, nicing the domain only affects the first and last value.
     *
     * Nicing a scale only modifies the current domain; it does not automatically nice domains that are subsequently set using continuous.domain.
     * You must re-nice the scale after setting the new domain, if desired.
     *
     * @param count An optional number of ticks expected to be used.
     */
    nice(count?: number): this;

    /**
     * Returns an exact copy of this scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleIdentity<NewUnknown>;
}

/**
 * Constructs a new identity scale with the specified domain and range.
 * If range is not specified, it defaults to [0, 1].
 *
 * The generic corresponds to the data type of the unknown value.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleIdentity<Unknown = never>(range?: Iterable<NumberValue>): ScaleIdentity<Unknown>;

// -------------------------------------------------------------------------------
// Radial Scale Factory
// -------------------------------------------------------------------------------

export interface ScaleRadial<Range, Output, Unknown = never> extends ScaleContinuousNumeric<Range, Output, Unknown> {
    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleRadial<Range, Output, NewUnknown>;
}

/**
 * Constructs a new radial scale with the specified range.
 * The domain defaults to [0, 1].
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the unknown value.
 *
 * The range must be set in accordance with the range element type.
 *
 * @param range Iterable of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleRadial<Range = number, Unknown = never>(
    range?: Iterable<Range>,
): ScaleRadial<Range, Range, Unknown>;
/**
 * Constructs a new radial scale with the specified domain and range.
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the unknown value.
 *
 * The range must be set in accordance with the range element type.
 *
 * @param domain Iterable of numeric domain values.
 * @param range Iterable of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleRadial<Range, Unknown = never>(
    domain: Iterable<NumberValue>,
    range: Iterable<Range>,
): ScaleRadial<Range, Range, Unknown>;

// -------------------------------------------------------------------------------
// Time Scale Factories
// -------------------------------------------------------------------------------

/**
 * A linear scale defined over a temporal domain.
 *
 * Time scales implement ticks based on calendar intervals, taking the pain out of generating axes for temporal domains.
 *
 * If the range is numeric, the mapping may be inverted to return a date.
 *
 * Note that the data types of the range and output of the scale must be compatible with the interpolator applied by the scale.
 *
 * The first generic corresponds to the data type of the range elements.
 *
 * The second generic corresponds to the data type of the output elements generated by the scale.
 *
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 */
export interface ScaleTime<Range, Output, Unknown = never> {
    /**
     * Given a value from the domain, returns the corresponding value from the range, subject to interpolation, if any.
     *
     * If the given value is outside the domain, and clamping is not enabled, the mapping may be extrapolated such that the returned value is outside the range.
     *
     * Note: The interpolation function applied by the scale may change the output type from the range type as part of the interpolation.
     *
     * @param value A temporal value from the domain. If the value is not a Date, it will be coerced to Date.
     */
    (value: Date | NumberValue): Output | Unknown;

    /**
     * Given a value from the range, returns the corresponding value from the domain. Inversion is useful for interaction,
     * say to determine the data value corresponding to the position of the mouse.
     *
     * If the given value is outside the range, and clamping is not enabled, the mapping may be extrapolated such that the returned value is outside the domain.
     *
     * IMPORTANT: This method is only supported if the range is numeric. If the range is not numeric, returns Invalid Date.
     *
     * For a valid value y in the range, time(time.invert(y)) equals y; similarly, for a valid value x in the domain, time.invert(time(x)) equals x.
     * The invert method is useful for interaction, say to determine the value in the domain that corresponds to the pixel location under the mouse.
     *
     * @param value A numeric value from the range.
     */
    invert(value: NumberValue): Date;

    /**
     * Returns a copy of the scale’s current domain.
     */
    domain(): Date[];

    /**
     * Sets the scale’s domain to the specified array of temporal domain values. The array must contain two or more elements.
     * If the elements in the given array are not dates, they will be coerced to dates.
     *
     * Although continuous scales typically have two values each in their domain and range, specifying more than two values produces a piecewise scale.
     *
     * Internally, a piecewise scale performs a binary search for the range interpolator corresponding to the given domain value.
     * Thus, the domain must be in ascending or descending order. If the domain and range have different lengths N and M, only the first min(N,M) elements in each are observed.
     *
     * @param domain Array of temporal domain values. Numeric values will be coerced to dates.
     */
    domain(domain: Iterable<Date | NumberValue>): this;

    /**
     * Returns a copy of the scale’s current range.
     */
    range(): Range[];
    /**
     * Sets the scale’s range to the specified array of values.
     *
     * The array must contain two or more elements. Unlike the domain, elements in the given array need not be temporal domain values;
     * any value that is supported by the underlying interpolator will work, though note that numeric ranges are required for invert.
     *
     * @param range Array of range values.
     */
    range(range: Iterable<Range>): this;

    /**
     * Sets the scale’s range to the specified array of values while also setting the scale’s interpolator to interpolateRound.
     *
     * The rounding interpolator is sometimes useful for avoiding antialiasing artifacts,
     * though also consider the shape-rendering “crispEdges” styles. Note that this interpolator can only be used with numeric ranges.
     *
     * The array must contain two or more elements. Unlike the domain, elements in the given array need not be temporal domain values;
     * any value that is supported by the underlying interpolator will work, though note that numeric ranges are required for invert.
     *
     * @param range Array of range values.
     */
    rangeRound(range: Iterable<NumberValue>): this;

    /**
     * Returns whether or not the scale currently clamps values to within the range.
     */
    clamp(): boolean;
    /**
     * Enables or disables clamping, respectively. If clamping is disabled and the scale is passed a value outside the domain,
     * the scale may return a value outside the range through extrapolation.
     *
     * If clamping is enabled, the return value of the scale is always within the scale’s range. Clamping similarly applies to the "invert" method.
     *
     * @param clamp A flag to enable (true) or disable (false) clamping.
     */
    clamp(clamp: boolean): this;

    /**
     * Returns the scale’s current interpolator factory, which defaults to interpolate.
     */
    interpolate(): InterpolatorFactory<any, any>;

    /**
     * Sets the scale’s range interpolator factory. This interpolator factory is used to create interpolators for each adjacent pair of values from the range;
     * these interpolators then map a normalized domain parameter t in [0, 1] to the corresponding value in the range.
     *
     * Note: the default interpolator may reuse return values. For example, if the range values are objects, then the value interpolator always returns the same object, modifying it in-place.
     * If the scale is used to set an attribute or style, this is typically acceptable (and desirable for performance);
     * however, if you need to store the scale’s return value, you must specify your own interpolator or make a copy as appropriate.
     *
     * As part of the interpolation process the interpolated value from the range may be converted to a corresponding output value.
     *
     * @param interpolate An interpolation factory. The generics for Range and Output of the scale must correspond to the interpolation factory applied to the scale.
     */
    interpolate(interpolate: InterpolatorFactory<Range, Output>): this;
    /**
     * Sets the scale’s range interpolator factory. This interpolator factory is used to create interpolators for each adjacent pair of values from the range;
     * these interpolators then map a normalized domain parameter t in [0, 1] to the corresponding value in the range.
     *
     * Note: the default interpolator may reuse return values. For example, if the range values are objects, then the value interpolator always returns the same object, modifying it in-place.
     * If the scale is used to set an attribute or style, this is typically acceptable (and desirable for performance);
     * however, if you need to store the scale’s return value, you must specify your own interpolator or make a copy as appropriate.
     *
     * As part of the interpolation process the interpolated value from the range may be converted to a corresponding output value.
     *
     * The generic "NewOutput" can be used to change the scale to have a different output element type corresponding to the new interpolation factory.
     *
     * @param interpolate An interpolation factory. The generics for Range and Output of the scale must correspond to the interpolation factory applied to the scale.
     */
    interpolate<NewOutput>(interpolate: InterpolatorFactory<Range, NewOutput>): ScaleTime<Range, NewOutput, Unknown>;

    /**
     * Returns representative dates from the scale’s domain. The returned tick values are uniformly-spaced (mostly),
     * have sensible values (such as every day at midnight), and are guaranteed to be within the extent of the domain.
     * Ticks are often used to display reference lines, or tick marks, in conjunction with the visualized data.
     *
     * An optional count may be specified to affect how many ticks are generated. If count is not specified, it defaults to 10.
     * The specified count is only a hint; the scale may return more or fewer values depending on the domain.
     *
     * @param count Expected number of ticks.
     */
    ticks(count?: number): Date[];
    /**
     * Returns representative dates from the scale’s domain. The returned tick values are uniformly-spaced (mostly),
     * have sensible values (such as every day at midnight), and are guaranteed to be within the extent of the domain.
     * Ticks are often used to display reference lines, or tick marks, in conjunction with the visualized data.
     *
     * The specified time interval controls the ticks generated and returned. To prune the generated ticks for a given time interval,
     * use interval.every(...) or interval.filter(...).
     *
     * @param interval A time interval to specify the expected ticks.
     */
    ticks(interval: TimeInterval): Date[];

    /**
     * Returns a time format function suitable for displaying tick values.
     *
     * The default multi-scale time format chooses a human-readable representation based on the specified date as follows:
     *
     *  - %Y - for year boundaries, such as 2011.
     *  - %B - for month boundaries, such as February.
     *  - %b %d - for week boundaries, such as Feb 06.
     *  - %a %d - for day boundaries, such as Mon 07.
     *  - %I %p - for hour boundaries, such as 01 AM.
     *  - %I:%M - for minute boundaries, such as 01:23.
     *  - :%S - for second boundaries, such as :45.
     *  - .%L - milliseconds for all other times, such as .012.
     *
     * Although somewhat unusual, this default behavior has the benefit of providing both local and global context:
     * for example, formatting a sequence of ticks as [11 PM, Mon 07, 01 AM] reveals information about hours, dates, and day simultaneously,
     * rather than just the hours [11 PM, 12 AM, 01 AM].
     *
     * The specified count is currently ignored, but is accepted for consistency with other scales such as continuous.tickFormat.
     *
     * @param count Expected number of ticks. (Currently ignored)
     * @param specifier An optional valid date format specifier string (see d3-time-format).
     */
    tickFormat(count?: number, specifier?: string): (d: Date) => string;
    /**
     * Returns a time format function suitable for displaying tick values.
     *
     * The specified time interval is currently ignored, but is accepted for consistency with other scales such as continuous.tickFormat.
     *
     * @param interval A time interval to specify the expected ticks. (Currently ignored)
     * @param specifier An optional valid date format specifier string (see d3-time-format).
     */
    tickFormat(interval: TimeInterval, specifier?: string): (d: Date) => string;

    /**
     * Extends the domain so that it starts and ends on nice round values.
     * This method typically modifies the scale’s domain, and may only extend the bounds to the nearest round value.
     *
     * An optional count argument allows greater control over the step size used to extend the bounds, guaranteeing that the returned ticks will exactly cover the domain.
     *
     * Nicing is useful if the domain is computed from data, say using extent, and may be irregular.
     * For example, for a domain of [2009-07-13T00:02, 2009-07-13T23:48], the nice domain is [2009-07-13, 2009-07-14].
     * If the domain has more than two values, nicing the domain only affects the first and last value.
     *
     * @param count Expected number of ticks.
     */
    nice(count?: number): this;
    /**
     * Extends the domain so that it starts and ends on nice round values.
     * This method typically modifies the scale’s domain, and may only extend the bounds to the nearest round value.
     *
     * A time interval may be specified to explicitly set the ticks.
     * If an interval is specified, an optional step may also be specified to skip some ticks.
     * For example, time.nice(d3.timeSecond.every(10)) will extend the domain to an even ten seconds (0, 10, 20, etc.).
     * See time.ticks and interval.every for further detail.
     *
     * Nicing is useful if the domain is computed from data, say using extent, and may be irregular.
     * For example, for a domain of [2009-07-13T00:02, 2009-07-13T23:48], the nice domain is [2009-07-13, 2009-07-14].
     * If the domain has more than two values, nicing the domain only affects the first and last value.
     *
     * @param interval A time interval to specify the expected ticks.
     */
    nice(interval: CountableTimeInterval): this;

    /**
     * Returns an exact copy of this scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleTime<Range, Output, NewUnknown>;
}

/**
 * Constructs a new time scale with the specified range, the default interpolator and clamping disabled.
 * The domain defaults to [2000-01-01, 2000-01-02].
 * If range is not specified, it defaults to [0, 1].
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleTime<Range = number, Output = Range, Unknown = never>(
    range?: Iterable<Range>,
): ScaleTime<Range, Output, Unknown>;
/**
 * Constructs a new time scale with the specified domain and range, the default interpolator and clamping disabled.
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param domain Array of temporal domain values. Numeric values will be coerced to dates.
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleTime<Range, Output = Range, Unknown = never>(
    domain: Iterable<Date | NumberValue>,
    range: Iterable<Range>,
): ScaleTime<Range, Output, Unknown>;

/**
 * Constructs a new time scale using Coordinated Universal Time (UTC) with the specified range, the default interpolator and clamping disabled.
 * The domain defaults to [2000-01-01, 2000-01-02].
 * If range is not specified, it defaults to [0, 1].
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleUtc<Range = number, Output = Range, Unknown = never>(
    range?: Iterable<Range>,
): ScaleTime<Range, Output, Unknown>;
/**
 * Constructs a new time scale using Coordinated Universal Time (UTC) with the specified domain and range, the default interpolator and clamping disabled.
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the output elements generated by the scale.
 * The third generic corresponds to the data type of the unknown value.
 *
 * If range element and output element type differ, the interpolator factory used with the scale must match this behavior and
 * convert the interpolated range element to a corresponding output element.
 *
 * The range must be set in accordance with the range element type.
 *
 * The interpolator factory may be set using the interpolate(...) method of the scale.
 *
 * @param domain Array of temporal domain values. Numeric values will be coerced to dates.
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleUtc<Range, Output = Range, Unknown = never>(
    domain: Iterable<NumberValue>,
    range: Iterable<Range>,
): ScaleTime<Range, Output, Unknown>;

// -------------------------------------------------------------------------------
// Sequential Scale Factory
// -------------------------------------------------------------------------------

/**
 * Sequential scales are similar to continuous scales in that they map a continuous, numeric input domain to a continuous output range.
 * However, unlike continuous scales, the input domain and output range of a sequential scale always has exactly two elements,
 * and the output range is typically specified as an interpolator rather than an array of values.
 * These scales do not expose invert and interpolate methods.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 *
 * The second generic corresponds to the data type of the unknown value.
 */
export interface ScaleSequentialBase<Output, Unknown = never> {
    /**
     * Given a value from the domain, returns the corresponding value from the output range, subject to interpolation.
     *
     * If the given value is outside the domain, and clamping is not enabled, the mapping may be extrapolated such that the returned value is outside the range.
     *
     * @param value A numeric value from the domain.
     */
    (value: NumberValue): Output | Unknown;

    /**
     * Returns a copy of the scale’s current domain.
     */
    domain(): [number, number];
    /**
     * Sets the scale’s domain to the specified array of numbers. The array must contain exactly two elements.
     * If the elements in the given array are not numbers, they will be coerced to numbers
     *
     * @param domain A two-element array of numeric domain values.
     */
    domain(domain: Iterable<NumberValue>): this;

    /**
     * Returns whether or not the scale currently clamps values to within the range.
     */
    clamp(): boolean;
    /**
     * Enables or disables clamping, respectively. If clamping is disabled and the scale is passed a value outside the domain,
     * the scale may return a value outside the range through extrapolation.
     *
     * If clamping is enabled, the return value of the scale is always within the scale’s range. Clamping similarly applies to the "invert" method.
     *
     * @param clamp A flag to enable (true) or disable (false) clamping.
     */
    clamp(clamp: boolean): this;

    /**
     * See continuous.range.
     */
    range(): [Output, Output];
    /**
     * See continuous.range.
     * The given two-element array is converted to an interpolator function using d3.interpolate.
     *
     * @param range Range values.
     */
    range(range: Iterable<Output>): this;

    /**
     * See continuous.rangeRound.
     * If range is specified, implicitly uses d3.interpolateRound as the interpolator.
     *
     * @param range Range values.
     */
    rangeRound(range: Iterable<NumberValue>): this;

    /**
     * Returns an exact copy of this scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;
}

export interface ScaleSequential<Output, Unknown = never> extends ScaleSequentialBase<Output, Unknown> {
    /**
     * Returns the current interpolator underlying the scale.
     */
    interpolator(): (t: number) => Output;
    /**
     * Sets the scale’s interpolator to the specified function.
     *
     * @param interpolator An interpolator function mapping a value from the [0, 1] interval to an output value.
     */
    interpolator(interpolator: (t: number) => Output): this;
    /**
     * Sets the scale’s interpolator to the specified function.
     *
     * The generic corresponds to a the new output type of the scale. The output type of the scale is determined by the output type of the interpolator function.
     *
     * @param interpolator An interpolator function mapping a value from the [0, 1] interval to an output value.
     */
    interpolator<NewOutput>(interpolator: (t: number) => NewOutput): ScaleSequential<NewOutput, Unknown>;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleSequential<Output, NewUnknown>;
}

/**
 * Constructs a new sequential scale with the specified interpolator function or array.
 * The domain defaults to [0, 1].
 * If interpolator is not specified, it defaults to the identity function.
 * When the scale is applied, the interpolator will be invoked with a value typically in the range [0, 1], where 0 represents the minimum value and 1 represents the maximum value.
 *
 * If interpolator is an array, it represents the scale’s two-element output range and is converted to an interpolator function using d3.interpolate.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The interpolator function or array to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequential<Output = number, Unknown = never>(
    interpolator?: ((t: number) => Output) | Iterable<Output>,
): ScaleSequential<Output, Unknown>;
/**
 * Constructs a new sequential scale with the specified domain and interpolator function or array.
 * When the scale is applied, the interpolator will be invoked with a value typically in the range [0, 1], where 0 represents the minimum value and 1 represents the maximum value.
 *
 * If interpolator is an array, it represents the scale’s two-element output range and is converted to an interpolator function using d3.interpolate.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain A two-element array of numeric domain values.
 * @param interpolator The interpolator function or array to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequential<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: ((t: number) => Output) | Iterable<Output>,
): ScaleSequential<Output, Unknown>;

/**
 * A sequential scale with a logarithmic transform, analogous to a log scale.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The interpolator function to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequentialLog<Output = number, Unknown = never>(
    interpolator?: (t: number) => Output,
): ScaleSequential<Output, Unknown>;
/**
 * A sequential scale with a logarithmic transform, analogous to a log scale.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain A two-element array of numeric domain values.
 * @param interpolator The interpolator function to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequentialLog<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: (t: number) => Output,
): ScaleSequential<Output, Unknown>;

/**
 * A sequential scale with a exponential transform, analogous to a power scale.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The interpolator function to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequentialPow<Output = number, Unknown = never>(
    interpolator?: (t: number) => Output,
): ScaleSequential<Output, Unknown>;
/**
 * A sequential scale with a exponential transform, analogous to a power scale.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain A two-element array of numeric domain values.
 * @param interpolator The interpolator function to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequentialPow<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: (t: number) => Output,
): ScaleSequential<Output, Unknown>;

/**
 * A sequential scale with a square-root transform, analogous to a d3.scaleSqrt.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second third generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The interpolator function to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequentialSqrt<Output = number, Unknown = never>(
    interpolator?: (t: number) => Output,
): ScaleSequential<Output, Unknown>;
/**
 * A sequential scale with a square-root transform, analogous to a d3.scaleSqrt.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain A two-element array of numeric domain values.
 * @param interpolator The interpolator function to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequentialSqrt<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: (t: number) => Output,
): ScaleSequential<Output, Unknown>;

/**
 * A sequential scale with a symmetric logarithmic transform, analogous to a symlog scale.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The interpolator function to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequentialSymlog<Output = number, Unknown = never>(
    interpolator?: (t: number) => Output,
): ScaleSequential<Output, Unknown>;
/**
 * A sequential scale with a symmetric logarithmic transform, analogous to a symlog scale.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain A two-element array of numeric domain values.
 * @param interpolator The interpolator function to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequentialSymlog<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: (t: number) => Output,
): ScaleSequential<Output, Unknown>;

export interface ScaleSequentialQuantile<Output, Unknown = never> extends ScaleSequentialBase<Output, Unknown> {
    /**
     * Returns an array of n + 1 quantiles.
     * For example, if n = 4, returns an array of five numbers: the minimum value, the first quartile, the median, the third quartile, and the maximum.
     */
    quantiles(): number[];

    /**
     * Returns the current interpolator underlying the scale.
     */
    interpolator(): (t: number) => Output;
    /**
     * Sets the scale’s interpolator to the specified function.
     *
     * @param interpolator An interpolator function mapping a value from the [0, 1] interval to an output value.
     */
    interpolator(interpolator: (t: number) => Output): this;
    /**
     * Sets the scale’s interpolator to the specified function.
     *
     * The generic corresponds to a the new output type of the scale. The output type of the scale is determined by the output type of the interpolator function.
     *
     * @param interpolator An interpolator function mapping a value from the [0, 1] interval to an output value.
     */
    interpolator<NewOutput>(interpolator: (t: number) => NewOutput): ScaleSequentialQuantile<NewOutput, Unknown>;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleSequentialQuantile<Output, NewUnknown>;
}

/**
 * A sequential scale using a p-quantile transform, analogous to a quantile scale.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The interpolator function to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequentialQuantile<Output = number, Unknown = never>(
    interpolator?: (t: number) => Output,
): ScaleSequentialQuantile<Output, Unknown>;
/**
 * A sequential scale using a p-quantile transform, analogous to a quantile scale.
 *
 * The first generic corresponds to the data type of the output of the interpolator underlying the scale.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain A two-element array of numeric domain values.
 * @param interpolator The interpolator function to be used with the scale.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleSequentialQuantile<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: (t: number) => Output,
): ScaleSequentialQuantile<Output, Unknown>;

// -------------------------------------------------------------------------------
// Diverging Scale Factory
// -------------------------------------------------------------------------------

/**
 * Diverging scales, like sequential scales, are similar to continuous scales in that they map a continuous, numeric input domain to a continuous output range.
 * However, unlike continuous scales, the input domain and output range of a diverging scale always has exactly three elements,
 * and the output range is typically specified as an interpolator rather than an array of values.
 * These scales do not expose invert and interpolate methods.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 *
 * The second generic corresponds to the data type of the unknown value.
 */
export interface ScaleDiverging<Output, Unknown = never> {
    /**
     * Given a value from the domain, returns the corresponding value subject to interpolation.
     *
     * If the given value is outside the domain, and clamping is not enabled, the mapping may be extrapolated such that the returned value is outside the range.
     *
     * @param value A numeric value from the domain.
     */
    (value: NumberValue): Output | Unknown;

    /**
     * Returns a copy of the scale’s current domain.
     */
    domain(): [number, number, number];
    /**
     * Sets the scale’s domain to the specified array of numbers.
     * The domain must be numeric and must contain exactly three values. The default domain is [0, 0.5, 1].
     * If the elements in the given array are not numbers, they will be coerced to numbers
     *
     * @param domain Array of three numeric domain values.
     */
    domain(domain: Iterable<NumberValue>): this;

    /**
     * Returns whether or not the scale currently clamps values to within the range.
     */
    clamp(): boolean;
    /**
     * Enables or disables clamping, respectively. If clamping is disabled and the scale is passed a value outside the domain,
     * the scale may return a value outside the range through extrapolation.
     *
     * If clamping is enabled, the return value of the scale is always within the interpolator scale’s range.
     *
     * @param clamp A flag to enable (true) or disable (false) clamping.
     */
    clamp(clamp: boolean): this;

    /**
     * Returns the scale’s current interpolator.
     */
    interpolator(): (t: number) => Output;
    /**
     * Sets the scale’s interpolator to the specified function.
     *
     * @param interpolator The scale’s interpolator.
     */
    interpolator(interpolator?: (t: number) => Output): this;

    /**
     * See continuous.range.
     */
    range(): [Output, Output, Output];
    /**
     * See continuous.range.
     * The given two-element array is converted to an interpolator function using d3.interpolate and d3.piecewise.
     *
     * @param range Range values.
     */
    range(range: Iterable<Output>): this;

    /**
     * See continuous.rangeRound.
     * If range is specified, implicitly uses d3.interpolateRound as the interpolator.
     *
     * @param range Range values.
     */
    rangeRound(range: Iterable<NumberValue>): this;

    /**
     * Returns an exact copy of this scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleDiverging<Output, NewUnknown>;
}

/**
 * Constructs a new diverging scale with the specified interpolator function or array.
 * The domain defaults to [0, 0.5, 1].
 * If interpolator is not specified, it defaults to the identity function.
 * When the scale is applied, the interpolator will be invoked with a value typically in the range [0, 1],
 * where 0 represents the extreme negative value, 0.5 represents the neutral value, and 1 represents the extreme positive value.
 *
 * If interpolator is an array, it represents the scale’s three-element output range and is converted to an interpolator function using d3.interpolate and d3.piecewise.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The scale’s interpolator function or array.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleDiverging<Output = number, Unknown = never>(
    interpolator?: ((t: number) => Output) | Iterable<Output>,
): ScaleDiverging<Output, Unknown>;
/**
 * Constructs a new diverging scale with the specified domain and interpolator function or array.
 * When the scale is applied, the interpolator will be invoked with a value typically in the range [0, 1],
 * where 0 represents the extreme negative value, 0.5 represents the neutral value, and 1 represents the extreme positive value.
 *
 * If interpolator is an array, it represents the scale’s three-element output range and is converted to an interpolator function using d3.interpolate and d3.piecewise.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain Array of three numeric domain values.
 * @param interpolator The scale’s interpolator function or array.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleDiverging<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: ((t: number) => Output) | Iterable<Output>,
): ScaleDiverging<Output, Unknown>;

/**
 * A diverging scale with a logarithmic transform, analogous to a log scale.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The scale’s interpolator.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleDivergingLog<Output = number, Unknown = never>(
    interpolator?: (t: number) => Output,
): ScaleDiverging<Output, Unknown>;
/**
 * A diverging scale with a logarithmic transform, analogous to a log scale.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain Array of three numeric domain values.
 * @param interpolator The scale’s interpolator.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleDivergingLog<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: (t: number) => Output,
): ScaleDiverging<Output, Unknown>;

/**
 * A diverging scale with a exponential transform, analogous to a power scale.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The scale’s interpolator.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleDivergingPow<Output = number, Unknown = never>(
    interpolator?: (t: number) => Output,
): ScaleDiverging<Output, Unknown>;
/**
 * A diverging scale with a exponential transform, analogous to a power scale.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain Array of three numeric domain values.
 * @param interpolator The scale’s interpolator.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleDivergingPow<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: (t: number) => Output,
): ScaleDiverging<Output, Unknown>;

/**
 * A diverging scale with a square-root transform, analogous to a d3.scaleSqrt.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The scale’s interpolator.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleDivergingSqrt<Output = number, Unknown = never>(
    interpolator?: (t: number) => Output,
): ScaleDiverging<Output, Unknown>;
/**
 * A diverging scale with a square-root transform, analogous to a d3.scaleSqrt.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain Array of three numeric domain values.
 * @param interpolator The scale’s interpolator.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleDivergingSqrt<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: (t: number) => Output,
): ScaleDiverging<Output, Unknown>;

/**
 * A diverging scale with a symmetric logarithmic transform, analogous to a symlog scale.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param interpolator The scale’s interpolator.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleDivergingSymlog<Output = number, Unknown = never>(
    interpolator?: (t: number) => Output,
): ScaleDiverging<Output, Unknown>;
/**
 * A diverging scale with a symmetric logarithmic transform, analogous to a symlog scale.
 *
 * The first generic corresponds to the data type of the interpolator return type.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain Array of three numeric domain values.
 * @param interpolator The scale’s interpolator.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleDivergingSymlog<Output, Unknown = never>(
    domain: Iterable<NumberValue>,
    interpolator: (t: number) => Output,
): ScaleDiverging<Output, Unknown>;

// -------------------------------------------------------------------------------
// Quantize Scale Factory
// -------------------------------------------------------------------------------

/**
 * Quantize scales are similar to linear scales, except they use a discrete rather than continuous range.
 * The continuous input domain is divided into uniform segments based on the number of values in (i.e., the cardinality of) the output range.
 *
 * Each range value y can be expressed as a quantized linear function of the domain value x: y = m round(x) + b.
 *
 * The first generic corresponds to the data type of the range elements.
 *
 * The second generic corresponds to the data type of the unknown value.
 */
export interface ScaleQuantize<Range, Unknown = never> {
    /**
     * Given a value in the input domain, returns the corresponding value in the output range.
     */
    (value: NumberValue): Range | Unknown;
    /**
     * Returns the extent of values in the domain [x0, x1] for the corresponding value in the range: the inverse of quantize.
     * This method is useful for interaction, say to determine the value in the domain that corresponds to the pixel location under the mouse.
     *
     * If an invalid range value is entered, returns [NaN, NaN].
     *
     * @param value A value from the range.
     */
    invertExtent(value: Range): [number, number];

    /**
     * Returns the scale’s current domain.
     */
    domain(): [number, number];

    /**
     * Sets the scale’s domain to the specified two-element array of numbers.
     * If the elements in the given array are not numbers, they will be coerced to numbers.
     *
     * @param domain A two-element array of numeric values defining the domain.
     */
    domain(domain: Iterable<NumberValue>): this;

    /**
     * Returns the scale’s current range.
     */
    range(): Range[];
    /**
     * Sets the scale’s range to the specified array of values. The array may contain any number of discrete values.
     *
     * @param range Array of range values.
     */
    range(range: Iterable<Range>): this;

    /**
     * Returns approximately count representative values from the scale’s domain.
     *
     * If count is not specified, it defaults to 10.
     *
     * The returned tick values are uniformly spaced, have human-readable values (such as multiples of powers of 10),
     * and are guaranteed to be within the extent of the domain. Ticks are often used to display reference lines, or tick marks, in conjunction with the visualized data.
     * The specified count is only a hint; the scale may return more or fewer values depending on the domain. See also d3-array’s ticks.
     *
     * @param count Optional approximate number of ticks to be returned. If count is not specified, it defaults to 10.
     */
    ticks(count?: number): number[];

    /**
     * Returns a number format function suitable for displaying a tick value, automatically computing the appropriate precision based on the fixed interval between tick values.
     * The specified count should have the same value as the count that is used to generate the tick values.
     *
     * @param count Approximate number of ticks to be used when calculating precision for the number format function.
     * @param specifier An optional valid format specifier string which allows a custom format where the precision of the format is automatically set by the scale as appropriate for the tick interval.
     * If specifier uses the format type "s", the scale will return a SI-prefix format based on the largest value in the domain.
     * If the specifier already specifies a precision, this method is equivalent to locale.format.
     */
    tickFormat(count?: number, specifier?: string): (d: NumberValue) => string;

    /**
     * Extends the domain so that it starts and ends on nice round values.
     * This method typically modifies the scale’s domain, and may only extend the bounds to the nearest round value.
     *
     * Nicing is useful if the domain is computed from data, say using extent, and may be irregular.
     * For example, for a domain of [0.201479…, 0.996679…], a nice domain might be [0.2, 1.0].
     *
     * Nicing a scale only modifies the current domain; it does not automatically nice domains that are subsequently set using continuous.domain.
     * You must re-nice the scale after setting the new domain, if desired.
     *
     * @param count An optional number of ticks expected to be used.
     */
    nice(count?: number): this;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleQuantize<Range, NewUnknown>;

    /**
     * Returns the array of computed thresholds within the domain.
     */
    thresholds(): number[];

    /**
     * Returns an exact copy of this scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;
}

/**
 * Constructs a new quantize scale with the specified range.
 * The domain defaults to [0, 1].
 * If range is not specified, it defaults to [0, 1].
 * Thus, the default quantize scale is equivalent to the Math.round function.
 *
 * The range must be set corresponding to the type of the range elements.
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleQuantize<Range = number, Unknown = never>(range?: Iterable<Range>): ScaleQuantize<Range, Unknown>;
/**
 * Constructs a new quantize scale with the specified domain and range.
 * Thus, the default quantize scale is equivalent to the Math.round function.
 *
 * The range must be set corresponding to the type of the range elements.
 *
 * The first generic corresponds to the data type of the range elements.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain A two-element array of numeric values defining the domain.
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleQuantize<Range, Unknown = never>(
    domain: Iterable<NumberValue>,
    range: Iterable<Range>,
): ScaleQuantize<Range, Unknown>;

// -------------------------------------------------------------------------------
// Quantile Scale Factory
// -------------------------------------------------------------------------------

/**
 * Quantile scales map a sampled input domain to a discrete range.
 * The domain is considered continuous and thus the scale will accept any reasonable input value;
 * however, the domain is specified as a discrete set of sample values.
 * The number of values in (the cardinality of) the output range determines the number of quantiles that will be computed from the domain.
 * To compute the quantiles, the domain is sorted, and treated as a population of discrete values; see d3-array’s quantile.
 *
 * The first generic corresponds to the data type of range elements.
 *
 * The second generic corresponds to the data type of the unknown value.
 */
export interface ScaleQuantile<Range, Unknown = never> {
    /**
     * Given a value in the input domain, returns the corresponding value in the output range.
     *
     * @param value A numeric value in the input domain.
     */
    (value: NumberValue): Range | Unknown;

    /**
     * Returns the extent of values in the domain [x0, x1] for the corresponding value in the range: the inverse of quantile.
     * This method is useful for interaction, say to determine the value in the domain that corresponds to the pixel location under the mouse.
     *
     * @param value A value from the range.
     */
    invertExtent(value: Range): [number, number];

    /**
     * Returns the scale’s current domain.
     */
    domain(): number[];
    /**
     * Sets the domain of the quantile scale to the specified set of discrete numeric values.
     * The array must not be empty, and must contain at least one numeric value; NaN, null and undefined values are ignored and not considered part of the sample population.
     *
     * If the elements in the given array are not numbers, they will be coerced to numbers. A copy of the input array is sorted and stored internally.
     *
     * @param domain Array of domain values.
     */
    domain(domain: Iterable<NumberValue | null | undefined>): this;

    /**
     * Returns the current range.
     */
    range(): Range[];
    /**
     * Sets the discrete values in the range. The array must not be empty.
     * The number of values in (the cardinality, or length, of) the range array determines the number of quantiles that are computed.
     *
     * For example, to compute quartiles, range must be an array of four elements such as [0, 1, 2, 3].
     *
     * @param range Array of range values.
     */
    range(range: Iterable<Range>): this;

    /**
     * Returns the quantile thresholds. If the range contains n discrete values, the returned array will contain n - 1 thresholds.
     * Values less than the first threshold are considered in the first quantile;
     * values greater than or equal to the first threshold but less than the second threshold are in the second quantile, and so on.
     * Internally, the thresholds array is used with bisect to find the output quantile associated with the given input value.
     */
    quantiles(): number[];

    /**
     * Returns an exact copy of this scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleQuantile<Range, NewUnknown>;
}

/**
 * Constructs a new quantile scale with the specified range.
 * The domain defaults to the empty array.
 * If range is not specified, it defaults to the empty array.
 * The quantile scale is invalid until both a domain and range are specified.
 *
 * The first generic corresponds to the data type of range elements.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleQuantile<Range = number, Unknown = never>(range?: Iterable<Range>): ScaleQuantile<Range, Unknown>;
/**
 * Constructs a new quantile scale with the specified domain and range.
 * The quantile scale is invalid until both a domain and range are specified.
 *
 * The first generic corresponds to the data type of range elements.
 * The second generic corresponds to the data type of the unknown value.
 *
 * @param domain Array of domain values.
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleQuantile<Range, Unknown = never>(
    domain: Iterable<NumberValue | null | undefined>,
    range: Iterable<Range>,
): ScaleQuantile<Range, Unknown>;

// -------------------------------------------------------------------------------
// Threshold Scale Factory
// -------------------------------------------------------------------------------

/**
 * Threshold scales are similar to quantize scales, except they allow you to map arbitrary subsets of the domain to discrete values in the range.
 * The input domain is still continuous, and divided into slices based on a set of threshold values.
 *
 * If the number of values in the scale’s range is N+1, the number of values in the scale’s domain must be N.
 * If there are fewer than N elements in the domain, the additional values in the range are ignored.
 * If there are more than N elements in the domain, the scale may return undefined for some inputs.
 *
 * The first generic corresponds to the data type of domain values.
 * The second generic corresponds to the data type of range values.
 * The third generic corresponds to the data type of the unknown value.
 */
export interface ScaleThreshold<Domain extends number | string | Date, Range, Unknown = never> {
    /**
     * Given a value in the input domain, returns the corresponding value in the output range.
     *
     * @param value A domain value.
     */
    (value: Domain): Range | Unknown;

    /**
     * Returns the extent of values in the domain [x0, x1] for the corresponding value in the range, representing the inverse mapping from range to domain.
     * This method is useful for interaction, say to determine the value in the domain that corresponds to the pixel location under the mouse.
     *
     * @param value A range value.
     */
    invertExtent(value: Range): [Domain | undefined, Domain | undefined];

    /**
     * Returns the scale’s current domain.
     */
    domain(): Domain[];
    /**
     * Sets the scale’s domain to the specified array of values. The values must be in sorted ascending order, or the behavior of the scale is undefined.
     * The values are typically numbers, but any naturally ordered values (such as strings) will work; a threshold scale can be used to encode any type that is ordered.
     * If the number of values in the scale’s range is N+1, the number of values in the scale’s domain must be N.
     * If there are fewer than N elements in the domain, the additional values in the range are ignored.
     * If there are more than N elements in the domain, the scale may return undefined for some inputs.
     *
     * @param domain Array of domain values.
     */
    domain(domain: Iterable<Domain>): this;

    /**
     * Returns the scale’s current range.
     */
    range(): Range[];
    /**
     * Sets the scale’s range to the specified array of values. If the number of values in the scale’s domain is N, the number of values in the scale’s range must be N+1.
     * If there are fewer than N+1 elements in the range, the scale may return undefined for some inputs.
     * If there are more than N+1 elements in the range, the additional values are ignored.
     *
     * @param range Array of range values.
     */
    range(range: Iterable<Range>): this;

    /**
     * Returns an exact copy of this scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;

    /**
     * Returns the current unknown value, which defaults to undefined.
     */
    unknown(): UnknownReturnType<Unknown, undefined>;
    /**
     * Sets the output value of the scale for undefined (or NaN) input values and returns this scale.
     *
     * @param value The output value of the scale for undefined (or NaN) input values.
     */
    unknown<NewUnknown>(value: NewUnknown): ScaleThreshold<Domain, Range, NewUnknown>;
}

/**
 * Constructs a new threshold scale with the specified range.
 * The domain defaults to [0.5].
 * If range is not specified, it defaults to [0, 1].
 * Thus, the default threshold scale is equivalent to the Math.round function for numbers; for example threshold(0.49) returns 0, and threshold(0.51) returns 1.
 *
 * The first generic corresponds to the data type of domain values.
 * The second generic corresponds to the data type of range values.
 * The third generic corresponds to the data type of the unknown value.
 *
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleThreshold<Domain extends number | string | Date = number, Range = number, Unknown = never>(
    range?: Iterable<Range>,
): ScaleThreshold<Domain, Range, Unknown>;
/**
 * Constructs a new threshold scale with the specified domain and range.
 * Thus, the default threshold scale is equivalent to the Math.round function for numbers; for example threshold(0.49) returns 0, and threshold(0.51) returns 1.
 *
 * The first generic corresponds to the data type of domain values.
 * The second generic corresponds to the data type of range values.
 * The third generic corresponds to the data type of the unknown value.
 *
 * @param domain Array of domain values.
 * @param range Array of range values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleThreshold<Domain extends number | string | Date, Range, Unknown = never>(
    domain: Iterable<Domain>,
    range: Iterable<Range>,
): ScaleThreshold<Domain, Range, Unknown>;

// -------------------------------------------------------------------------------
// Ordinal Scale Factory
// -------------------------------------------------------------------------------

/**
 * Unlike continuous scales, ordinal scales have a discrete domain and range. For example, an ordinal scale might map a set of named categories to a set of colors,
 * or determine the horizontal positions of columns in a column chart.
 *
 * The first element in the domain will be mapped to the first element in range, the second domain value to the second range value, and so on.
 * If there are fewer elements in the range than in the domain, the scale will reuse values from the start of the range.
 *
 * The first generic corresponds to the data type of domain values.
 * The second generic corresponds to the data type of range values.
 * The third generic corresponds to the data type of the unknown value.
 */
export interface ScaleOrdinal<Domain extends { toString(): string }, Range, Unknown = never> {
    /**
     * Given a value in the input domain, returns the corresponding value in the output range.
     * If the given value is not in the scale’s domain, returns the unknown; or, if the unknown value is implicit (the default),
     * then the value is implicitly added to the domain and the next-available value in the range is assigned to value,
     * such that this and subsequent invocations of the scale given the same input value return the same output value.
     *
     * @param x A value from the domain.
     */
    (x: Domain): Range | Unknown;

    /**
     * Returns the scale's current domain.
     */
    domain(): Domain[];
    /**
     * Sets the domain to the specified array of values.
     *
     * The first element in domain will be mapped to the first element in the range,
     * the second domain value to the second range value, and so on.
     *
     * Domain values are stored internally in an InternMap from primitive value to index; the resulting index is then used to retrieve a value from the range.
     * Thus, an ordinal scale’s values must be coercible to a primitive value, and the primitive domain value uniquely identifies the corresponding range value.
     *
     * Setting the domain on an ordinal scale is optional if the unknown value is implicit (the default).
     * In this case, the domain will be inferred implicitly from usage by assigning each unique value passed to the scale a new value from the range.
     * Note that an explicit domain is recommended to ensure deterministic behavior, as inferring the domain from usage will be dependent on ordering.
     *
     * @param domain Array of domain values.
     */
    domain(domain: Iterable<Domain>): this;

    /**
     * Returns the scale's current range.
     */
    range(): Range[];
    /**
     * Sets the range of the ordinal scale to the specified array of values.
     *
     * The first element in the domain will be mapped to the first element in range, the second domain value to the second range value, and so on.
     *
     * If there are fewer elements in the range than in the domain, the scale will reuse values from the start of the range.
     *
     * @param range Array of range values.
     */
    range(range: Iterable<Range>): this;

    /**
     * Returns the current unknown value, which defaults to "implicit".
     */
    unknown(): UnknownReturnType<Unknown, { name: "implicit" }>;
    /**
     * Sets the output value of the scale for unknown input values and returns this scale.
     * The implicit value enables implicit domain construction. scaleImplicit can be used as a convenience to set the implicit value.
     *
     * @param value Unknown value to be used or scaleImplicit to set implicit scale generation.
     */
    unknown<NewUnknown>(
        value: NewUnknown,
    ): NewUnknown extends { name: "implicit" } ? ScaleOrdinal<Domain, Range>
        : ScaleOrdinal<Domain, Range, NewUnknown>;

    /**
     * Returns an exact copy of this ordinal scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;
}

/**
 * Constructs a new ordinal scale with the specified range.
 * The domain defaults to the empty array.
 * If range is not specified, it defaults to the empty array; an ordinal scale always returns undefined until a non-empty range is defined.
 *
 * The generic corresponds to the data type of range elements.
 *
 * @param range An optional array of range values to initialize the scale with.
 */
export function scaleOrdinal<Range>(range?: Iterable<Range>): ScaleOrdinal<string, Range>;
/**
 * Constructs a new ordinal scale with the specified range.
 * The domain defaults to the empty array.
 * If range is not specified, it defaults to the empty array; an ordinal scale always returns undefined until a non-empty range is defined.
 *
 * The first generic corresponds to the data type of domain elements.
 * The second generic corresponds to the data type of range elements.
 * The third generic corresponds to the data type of the unknown value.
 *
 * @param range An optional array of range values to initialize the scale with.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleOrdinal<Domain extends { toString(): string }, Range, Unknown = never>(
    range?: Iterable<Range>,
): ScaleOrdinal<Domain, Range, Unknown>;
/**
 * Constructs a new ordinal scale with the specified domain and range.
 *
 * The first generic corresponds to the data type of domain elements.
 * The second generic corresponds to the data type of range elements.
 * The third generic corresponds to the data type of the unknown value.
 *
 * @param domain Array of domain values.
 * @param range An optional array of range values to initialize the scale with.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleOrdinal<Domain extends { toString(): string }, Range, Unknown = never>(
    domain: Iterable<Domain>,
    range: Iterable<Range>,
): ScaleOrdinal<Domain, Range, Unknown>;

/**
 * A special value for ordinal.unknown that enables implicit domain construction: unknown values are implicitly added to the domain.
 */
export const scaleImplicit: { name: "implicit" };

// -------------------------------------------------------------------------------
// Band Scale Factory
// -------------------------------------------------------------------------------

/**
 * Band scales are like ordinal scales except the output range is continuous and numeric.
 * Discrete output values are automatically computed by the scale by dividing the continuous range into uniform bands.
 * Band scales are typically used for bar charts with an ordinal or categorical dimension.
 * The unknown value of a band scale is effectively undefined: they do not allow implicit domain construction.
 *
 * The generic corresponds to the data type of domain elements.
 */
export interface ScaleBand<Domain extends { toString(): string }> {
    /**
     * Given a value in the input domain, returns the start of the corresponding band derived from the output range.
     * If the given value is not in the scale’s domain, returns undefined.
     *
     * @param x  A value from the domain.
     */
    (x: Domain): number | undefined;

    /**
     * Returns to scale's current domain
     */
    domain(): Domain[];
    /**
     * Sets the domain to the specified array of values. The first element in domain will be mapped to the first band, the second domain value to the second band, and so on.
     * Domain values are stored internally in an InternMap from primitive value to index; the resulting index is then used to determine the band.
     * Thus, a band scale’s values must be coercible to a primitive value, and the primitive domain value uniquely identifies the corresponding band.
     *
     * @param domain Array of domain values.
     */
    domain(domain: Iterable<Domain>): this;

    /**
     * Returns the scale’s current range, which defaults to [0, 1].
     */
    range(): [number, number];
    /**
     * Sets the scale’s range to the specified two-element array of numbers. If the elements in the given array are not numbers, they will be coerced to numbers.
     * The default range is [0, 1].
     *
     * @param range A two-element array of numeric values.
     */
    range(range: Iterable<NumberValue>): this;

    /**
     * Sets the scale’s range to the specified two-element array of numbers while also enabling rounding.
     * If the elements in the given array are not numbers, they will be coerced to numbers.
     *
     * Rounding is sometimes useful for avoiding antialiasing artifacts, though also consider the shape-rendering “crispEdges” styles.
     *
     * @param range A two-element array of numeric values.
     */
    rangeRound(range: Iterable<NumberValue>): this;

    /**
     * Returns the current rounding status for the scale: enabled (= true) or disabled (= false).
     */
    round(): boolean;
    /**
     * Enables or disables rounding accordingly. If rounding is enabled, the start and stop of each band will be integers.
     * Rounding is sometimes useful for avoiding antialiasing artifacts, though also consider the shape-rendering “crispEdges” styles.
     * Note that if the width of the domain is not a multiple of the cardinality of the range, there may be leftover unused space, even without padding!
     * Use band.align to specify how the leftover space is distributed.
     *
     * @param round Enable rounding (= true), disable rounding (= false).
     */
    round(round: boolean): this;

    /**
     * Returns the current inner padding which defaults to 0.
     */
    paddingInner(): number;
    /**
     * Sets the inner padding to the specified value which must be in the range [0, 1].
     * The inner padding determines the ratio of the range that is reserved for blank space between bands.
     *
     * The default setting is 0.
     *
     * @param padding Value for inner padding in [0, 1] interval.
     */
    paddingInner(padding: number): this;

    /**
     * Returns the current outer padding which defaults to 0.
     */
    paddingOuter(): number;
    /**
     * Sets the outer padding to the specified value which must be in the range [0, 1].
     * The outer padding determines the ratio of the range that is reserved for blank space before the first band and after the last band.
     *
     * The default setting is 0.
     *
     * @param padding Value for outer padding in [0, 1] interval.
     */
    paddingOuter(padding: number): this;

    /**
     * Returns the inner padding.
     */
    padding(): number;
    /**
     * A convenience method for setting the inner and outer padding to the same padding value.
     *
     * @param padding Value for inner and outer padding in [0, 1] interval.
     */
    padding(padding: number): this;

    /**
     * Returns the current alignment which defaults to 0.5.
     */
    align(): number;
    /**
     * Sets the alignment to the specified value which must be in the range [0, 1].
     *
     * The default is 0.5.
     *
     * The alignment determines how any leftover unused space in the range is distributed.
     * A value of 0.5 indicates that the outer patter should be equally distributed before the first band and after the last band;
     * i.e., the bands should be centered within the range. A value of 0 or 1 may be used to shift the bands to one side, say to position them adjacent to an axis.
     *
     * @param align Value for alignment setting in [0, 1] interval.
     */
    align(align: number): this;

    /**
     * Returns the width of each band.
     */
    bandwidth(): number;

    /**
     * Returns the distance between the starts of adjacent bands.
     */
    step(): number;

    /**
     * Returns an exact copy of this scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;
}

/**
 * Constructs a new band scale with the specified range, no padding, no rounding and center alignment.
 * The domain defaults to the empty domain.
 * If range is not specified, it defaults to the unit range [0, 1].
 *
 * The generic corresponds to the data type of domain elements.
 *
 * @param range A two-element array of numeric values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scaleBand<Domain extends { toString(): string } = string>(
    range?: Iterable<NumberValue>,
): ScaleBand<Domain>;
/**
 * Constructs a new band scale with the specified domain and range, no padding, no rounding and center alignment.
 *
 * The generic corresponds to the data type of domain elements.
 *
 * @param domain Array of domain values.
 * @param range A two-element array of numeric values.
 */
export function scaleBand<Domain extends { toString(): string }>(
    domain: Iterable<Domain>,
    range: Iterable<NumberValue>,
): ScaleBand<Domain>;

// -------------------------------------------------------------------------------
// Point Scale Factory
// -------------------------------------------------------------------------------

/**
 * Point scales are a variant of band scales with the bandwidth fixed to zero.
 * Point scales are typically used for scatterplots with an ordinal or categorical dimension.
 * The unknown value of a point scale is always undefined: they do not allow implicit domain construction.
 *
 * The generic corresponds to the data type of domain elements.
 */
export interface ScalePoint<Domain extends { toString(): string }> {
    /**
     * Given a value in the input domain, returns the corresponding point derived from the output range.
     * If the given value is not in the scale’s domain, returns undefined.
     *
     * @param x  A value from the domain.
     */
    (x: Domain): number | undefined;

    /**
     * Returns the scale's current domain.
     */
    domain(): Domain[];
    /**
     * Sets the domain to the specified array of values. The first element in domain will be mapped to the first point, the second domain value to the second point, and so on.
     * Domain values are stored internally in an InternMap from primitive value to index; the resulting index is then used to determine the point.
     * Thus, a point scale’s values must be coercible to a primitive value, and the primitive domain value uniquely identifies the corresponding point.
     *
     * @param domain Array of domain values.
     */
    domain(domain: Iterable<Domain>): this;

    /**
     * Returns the scale’s current range, which defaults to [0, 1].
     */
    range(): [number, number];
    /**
     * Sets the scale’s range to the specified two-element array of numbers.
     * If the elements in the given array are not numbers, they will be coerced to numbers.
     * The default range is [0, 1].
     *
     * @param range A two-element array of numeric values.
     */
    range(range: Iterable<NumberValue>): this;

    /**
     * Sets the scale’s range to the specified two-element array of numbers while also enabling rounding.
     * If the elements in the given array are not numbers, they will be coerced to numbers.
     *
     * Rounding is sometimes useful for avoiding antialiasing artifacts, though also consider the shape-rendering “crispEdges” styles.
     *
     * @param range A two-element array of numeric values.
     */
    rangeRound(range: Iterable<NumberValue>): this;

    /**
     * Returns the current rounding status for the scale: enabled (= true) or disabled (= false).
     */
    round(): boolean;
    /**
     * Enables or disables rounding accordingly. If rounding is enabled, the position of each point will be integers.
     * Rounding is sometimes useful for avoiding antialiasing artifacts, though also consider the shape-rendering “crispEdges” styles.
     * Note that if the width of the domain is not a multiple of the cardinality of the range, there may be leftover unused space, even without padding!
     * Use point.align to specify how the leftover space is distributed.
     *
     * @param round Enable rounding (= true), disable rounding (= false).
     */
    round(round: boolean): this;

    /**
     * Returns the current outer padding which defaults to 0.
     * The outer padding determines the ratio of the range that is reserved for blank space
     * before the first point and after the last point.
     */
    padding(): number;
    /**
     * Sets the outer padding to the specified value which must be in the range [0, 1].
     * The outer padding determines the ratio of the range that is reserved for blank space
     * before the first point and after the last point.
     *
     * The default is 0.
     *
     * @param padding Value for outer padding in [0, 1] interval.
     */
    padding(padding: number): this;

    /**
     * Returns the current alignment which defaults to 0.5.
     */
    align(): number;
    /**
     * Sets the alignment to the specified value which must be in the range [0, 1].
     *
     * The alignment determines how any leftover unused space in the range is distributed.
     * A value of 0.5 indicates that the leftover space should be equally distributed before the first point and after the last point;
     * i.e., the points should be centered within the range. A value of 0 or 1 may be used to shift the points to one side, say to position them adjacent to an axis.
     *
     * The default value is 0.5.
     *
     * @param align Value for alignment setting in [0, 1] interval.
     */
    align(align: number): this;

    /**
     * Return 0.
     */
    bandwidth(): number;

    /**
     * Returns the distance between the starts of adjacent points.
     */
    step(): number;

    /**
     * Returns an exact copy of this scale. Changes to this scale will not affect the returned scale, and vice versa.
     */
    copy(): this;
}

/**
 * Constructs a new point scale with the specified range, no padding, no rounding and center alignment.
 * The domain defaults to the empty domain.
 * If range is not specified, it defaults to the unit range [0, 1].
 *
 * The generic corresponds to the data type of domain elements.
 *
 * @param range A two-element array of numeric values.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function scalePoint<Domain extends { toString(): string } = string>(
    range?: Iterable<NumberValue>,
): ScalePoint<Domain>;
/**
 * Constructs a new point scale with the specified domain and range, no padding, no rounding and center alignment.
 * The domain defaults to the empty domain.
 *
 * The generic corresponds to the data type of domain elements.
 *
 * @param domain Array of domain values.
 * @param range A two-element array of numeric values.
 */
export function scalePoint<Domain extends { toString(): string }>(
    domain: Iterable<Domain>,
    range: Iterable<NumberValue>,
): ScalePoint<Domain>;
