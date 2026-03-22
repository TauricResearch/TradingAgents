// Last module patch version validated against: 3.0.0

import { Selection, TransitionLike } from "d3-selection";

// --------------------------------------------------------------------------
// Shared Types and Interfaces
// --------------------------------------------------------------------------

/**
 * A helper type to alias elements which can serve as a domain for an axis.
 */
export type AxisDomain = number | string | Date | { valueOf(): number };

/**
 * A helper interface to describe the minimal contract to be met by a time interval
 * which can be passed into the Axis.ticks(...) or Axis.tickArguments(...) methods when
 * creating time series axes. Under normal circumstances the argument will be of type
 * TimeInterval or CountableTimeInterval as defined in d3-time.
 * NB: This helper interface has been created to avoid tight coupling of d3-axis to
 * d3-time at the level of definition files. I.e. d3-time is not a
 * dependency of d3-axis in the D3 Javascript implementation. This minimal contract
 * is based on an analysis of how d3-axis passes a time interval argument into a time scale,
 * if a time scale was set using Axis.scale(...). And in turn on how a time scale uses
 * the time interval when creating ticks from it.
 */
export interface AxisTimeInterval {
    range(start: Date, stop: Date, step?: number): Date[];
}

/**
 * A helper interface to which a scale passed into axis must conform (at a minimum)
 * for axis to use the scale without error.
 */
export interface AxisScale<Domain> {
    (x: Domain): number | undefined;
    domain(): Domain[];
    range(): number[];
    copy(): this;
    bandwidth?(): number;
    // TODO: Reconsider the below, note that the compiler does not differentiate the overloads w.r.t. optionality
    // ticks?(count?: number): Domain[];
    // ticks?(count?: AxisTimeInterval): Date[];
    // tickFormat?(count?: number, specifier?: string): ((d: number) => string);
    // tickFormat?(count?: number | AxisTimeInterval, specifier?: string): ((d: Date) => string);
}

/**
 * A helper type to alias elements which can serve as a container for an axis.
 */
export type AxisContainerElement = SVGSVGElement | SVGGElement;

/**
 * Interface defining an axis generator. The generic <Domain> is the type of the axis domain.
 */
export interface Axis<Domain> {
    /**
     * Render the axis to the given context.
     *
     * @param context A selection of or a transition defined on SVG containers (either SVG or G elements).
     */
    (
        context:
            | Selection<SVGSVGElement, any, any, any>
            | Selection<SVGGElement, any, any, any>
            | TransitionLike<SVGSVGElement, any>
            | TransitionLike<SVGGElement, any>,
    ): void;

    /**
     * Gets the current scale underlying the axis.
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    scale<A extends AxisScale<Domain>>(): A;

    /**
     * Sets the scale and returns the axis.
     *
     * @param scale The scale to be used for axis generation.
     */
    scale(scale: AxisScale<Domain>): this;

    /**
     * Sets the arguments that will be passed to scale.ticks and scale.tickFormat when the axis is rendered, and returns the axis generator.
     *
     * This method has no effect if the scale does not implement scale.ticks, as with band and point scales.
     *
     * This method is also a convenience function for axis.tickArguments.
     *
     * @param count Number of ticks that should be rendered.
     * @param specifier An optional format specifier to customize how the tick values are formatted.
     */
    ticks(count: number, specifier?: string): this;

    /**
     * Sets the arguments that will be passed to scale.ticks and scale.tickFormat when the axis is rendered, and returns the axis generator.
     * Use with a TIME SCALE ONLY.
     *
     * This method is also a convenience function for axis.tickArguments.
     *
     * @param interval A time interval used to generate date-based ticks. This is typically a TimeInterval/CountableTimeInterval as defined
     * in d3-time. E.g. as obtained by passing in d3.timeMinute.every(15).
     * @param specifier An optional format specifier to customize how the tick values are formatted.
     */
    // tslint:disable-next-line:unified-signatures
    ticks(interval: AxisTimeInterval, specifier?: string): this;

    /**
     * Sets the arguments that will be passed to scale.ticks and scale.tickFormat when the axis is rendered, and returns the axis generator.
     *
     * The meaning of the arguments depends on the axis’ scale type: most commonly, the arguments are a suggested count for the number of ticks
     * (or a time interval for time scales), and an optional format specifier to customize how the tick values are formatted.
     *
     * This method has no effect if the scale does not implement scale.ticks, as with band and point scales.
     *
     * To set the tick values explicitly, use axis.tickValues. To set the tick format explicitly, use axis.tickFormat.
     *
     * This method is also a convenience function for axis.tickArguments.
     */
    ticks(arg0: any, ...args: any[]): this;

    /**
     * Get an array containing the currently set arguments to be passed into scale.ticks and scale.tickFormat, which defaults to the empty array.
     */
    tickArguments(): any[];

    /**
     * Sets the arguments that will be passed to scale.ticks and scale.tickFormat when the axis is rendered, and returns the axis generator.
     *
     * This method has no effect if the scale does not implement scale.ticks, as with band and point scales.
     * To set the tick values explicitly, use axis.tickValues. To set the tick format explicitly, use axis.tickFormat.
     *
     * See also axis.ticks.
     *
     * @param args The meaning of the arguments depends on the axis’ scale type: most commonly, the arguments are a
     * suggested count for the number of ticks (or a time interval for time scales), and an optional format specifier to
     * customize how the tick values are formatted.
     */
    tickArguments(args: any[]): this;

    /**
     * Returns the current tick values, which defaults to null.
     */
    tickValues(): Domain[] | null;

    /**
     * Specified values to be used for ticks rather than using the scale’s automatic tick generator.
     * The explicit tick values take precedent over the tick arguments set by axis.tickArguments.
     * However, any tick arguments will still be passed to the scale’s tickFormat function if a
     * tick format is not also set.
     *
     * @param values An iterable with values from the Domain of the scale underlying the axis.
     */
    tickValues(values: Iterable<Domain>): this;

    /**
     * Clears any previously-set explicit tick values and reverts back to the scale’s tick generator.
     *
     * @param values null
     */
    tickValues(values: null): this;

    /**
     * Returns the currently set tick format function, which defaults to null.
     */
    tickFormat(): ((domainValue: Domain, index: number) => string) | null;

    /**
     * Sets the tick format function and returns the axis.
     *
     * @param format A function mapping a value from the axis Domain to a formatted string
     * for display purposes. When invoked, the format function is also passed a second argument representing the zero-based index
     * of the tick label in the array of generated tick labels.
     */
    tickFormat(format: (domainValue: Domain, index: number) => string): this;

    /**
     * Reset the tick format function. A null format indicates that the scale’s
     * default formatter should be used, which is generated by calling scale.tickFormat.
     * In this case, the arguments specified by axis.tickArguments
     * are likewise passed to scale.tickFormat.
     *
     * @param format null
     */
    tickFormat(format: null): this;

    /**
     * Get the current inner tick size, which defaults to 6.
     */
    tickSize(): number;
    /**
     * Set the inner and outer tick size to the specified value and return the axis.
     *
     * @param size Tick size in pixels (Default is 6).
     */
    tickSize(size: number): this;

    /**
     * Get the current inner tick size, which defaults to 6.
     * The inner tick size controls the length of the tick lines,
     * offset from the native position of the axis.
     */
    tickSizeInner(): number;

    /**
     * Set the inner tick size to the specified value and return the axis.
     * The inner tick size controls the length of the tick lines,
     * offset from the native position of the axis.
     *
     * @param size Tick size in pixels (Default is 6).
     */
    tickSizeInner(size: number): this;

    /**
     * Get the current outer tick size, which defaults to 6.
     * The outer tick size controls the length of the square ends of the domain path,
     * offset from the native position of the axis. Thus, the “outer ticks” are not actually
     * ticks but part of the domain path, and their position is determined by the associated
     * scale’s domain extent. Thus, outer ticks may overlap with the first or last inner tick.
     * An outer tick size of 0 suppresses the square ends of the domain path,
     * instead producing a straight line.
     */
    tickSizeOuter(): number;

    /**
     * Set the current outer tick size and return the axis.
     * The outer tick size controls the length of the square ends of the domain path,
     * offset from the native position of the axis. Thus, the “outer ticks” are not actually
     * ticks but part of the domain path, and their position is determined by the associated
     * scale’s domain extent. Thus, outer ticks may overlap with the first or last inner tick.
     * An outer tick size of 0 suppresses the square ends of the domain path,
     * instead producing a straight line.
     *
     * @param size Tick size in pixels (Default is 6).
     */
    tickSizeOuter(size: number): this;

    /**
     * Get the current padding, which defaults to 3.
     */
    tickPadding(): number;

    /**
     * Set the current padding and return the axis.
     *
     * @param padding Padding in pixels (Default is 3).
     */
    tickPadding(padding: number): this;

    /**
     * Returns the current offset which defaults to 0 on devices with a devicePixelRatio greater than 1, and 0.5px otherwise.
     * This default offset ensures crisp edges on low-resolution devices.
     */
    offset(): number;

    /**
     * Sets the offset to the specified value in pixels and returns the axis.
     * Defaults to 0 on devices with a devicePixelRatio greater than 1, and 0.5px otherwise.
     * This default offset ensures crisp edges on low-resolution devices.
     */
    offset(offset: number): this;
}

/**
 * Constructs a new top-oriented axis generator for the given scale, with empty tick arguments,
 * a tick size of 6 and padding of 3. In this orientation, ticks are drawn above the horizontal domain path.
 *
 * @param scale The scale to be used for axis generation.
 */
export function axisTop<Domain extends AxisDomain>(scale: AxisScale<Domain>): Axis<Domain>;

/**
 * Constructs a new right-oriented axis generator for the given scale, with empty tick arguments,
 * a tick size of 6 and padding of 3. In this orientation, ticks are drawn to the right of the vertical domain path.
 *
 * @param scale The scale to be used for axis generation.
 */
export function axisRight<Domain extends AxisDomain>(scale: AxisScale<Domain>): Axis<Domain>;

/**
 * Constructs a new bottom-oriented axis generator for the given scale, with empty tick arguments,
 * a tick size of 6 and padding of 3. In this orientation, ticks are drawn below the horizontal domain path.
 *
 * @param scale The scale to be used for axis generation.
 */
export function axisBottom<Domain extends AxisDomain>(scale: AxisScale<Domain>): Axis<Domain>;

/**
 * Constructs a new left-oriented axis generator for the given scale, with empty tick arguments,
 * a tick size of 6 and padding of 3. In this orientation, ticks are drawn to the left of the vertical domain path.
 *
 * @param scale The scale to be used for axis generation.
 */
export function axisLeft<Domain extends AxisDomain>(scale: AxisScale<Domain>): Axis<Domain>;
