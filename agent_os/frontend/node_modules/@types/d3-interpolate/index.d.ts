// Last module patch version validated against: 3.0.1

import { ColorCommonInstance } from "d3-color";

// ---------------------------------------------------------------------------
// Shared Type Definitions and Interfaces
// ---------------------------------------------------------------------------

export interface ZoomInterpolator extends Function {
    (t: number): ZoomView;
    /**
     * Recommended duration of zoom transition in milliseconds.
     */
    duration: number;

    /**
     * Given a zoom interpolator, returns a new zoom interpolator using the specified curvature rho.
     * When rho is close to 0, the interpolator is almost linear.
     * The default curvature is sqrt(2).
     * @param rho
     */
    rho(rho: number): this;
}

export interface ColorGammaInterpolationFactory extends Function {
    (a: string | ColorCommonInstance, b: string | ColorCommonInstance): (t: number) => string;
    /**
     * Returns a new interpolator factory of the same type using the specified *gamma*.
     * For example, to interpolate from purple to orange with a gamma of 2.2 in RGB space: `d3.interpolateRgb.gamma(2.2)("purple", "orange")`.
     * See Eric Brasseur’s article, [Gamma error in picture scaling](https://web.archive.org/web/20160112115812/http://www.4p8.com/eric.brasseur/gamma.html), for more on gamma correction.
     */
    gamma(g: number): ColorGammaInterpolationFactory;
}

/**
 * Type zoomView is used to represent a numeric array with three elements.
 * In order of appearance the elements correspond to:
 * - cx: *x*-coordinate of the center of the viewport
 * - cy: *y*-coordinate of the center of the viewport
 * - width: size of the viewport
 */
export type ZoomView = [number, number, number];

export type TypedArray =
    | Int8Array
    | Uint8Array
    | Int16Array
    | Uint16Array
    | Int32Array
    | Uint32Array
    | Uint8ClampedArray
    | Float32Array
    | Float64Array;

export type NumberArray = TypedArray | DataView;

// ---------------------------------------------------------------------------
// Interpolation Function Factories
// ---------------------------------------------------------------------------

/**
 * Returns an `null` constant interpolator.
 */
export function interpolate(a: any, b: null): (t: number) => null;
/**
 * Returns an boolean constant interpolator of value `b`.
 */
export function interpolate(a: any, b: boolean): (t: number) => boolean;
/**
 * Returns a `interpolateRgb` interpolator.
 */
export function interpolate(a: string | ColorCommonInstance, b: ColorCommonInstance): (t: number) => string;
/**
 * Returns a `interpolateDate` interpolator.
 */
export function interpolate(a: Date, b: Date): (t: number) => Date;
/**
 * Returns a `interpolateNumber` interpolator.
 */
export function interpolate(
    a: number | { valueOf(): number },
    b: number | { valueOf(): number },
): (t: number) => number;
/**
 * Returns a `interpolateNumberArray` interpolator.
 */
export function interpolate<T extends NumberArray>(a: NumberArray | number[], b: T): (t: number) => T;
/**
 * Returns a `interpolateString` interpolator. If `b` is a string coercible to a color use use `interpolateRgb`.
 */
export function interpolate(a: string | { toString(): string }, b: string): (t: number) => string;
/**
 * Returns a `interpolateArray` interpolator.
 */
export function interpolate<U extends any[]>(a: any[], b: U): (t: number) => U;
/**
 * Returns a `interpolateObject` interpolator.
 */
export function interpolate<U extends object>(a: any, b: U): (t: number) => U;

/**
 * Returns an interpolator between the two numbers `a` and `b`.
 * The returned interpolator is equivalent to: `(t) => a * (1 - t) + b * t`.
 */
export function interpolateNumber(
    a: number | { valueOf(): number },
    b: number | { valueOf(): number },
): (t: number) => number;

/**
 * Returns an interpolator between the two numbers `a` and `b`; the interpolator is similar to `interpolateNumber`,
 * except it will round the resulting value to the nearest integer.
 */
export function interpolateRound(
    a: number | { valueOf(): number },
    b: number | { valueOf(): number },
): (t: number) => number;

/**
 * Returns an interpolator between the two strings `a` and `b`.
 * The string interpolator finds numbers embedded in `a` and `b`, where each number is of the form understood by JavaScript.
 * A few examples of numbers that will be detected within a string: `-1`, `42`, `3.14159`, and `6.0221413e+23`.
 *
 * For each number embedded in `b`, the interpolator will attempt to find a corresponding number in `a`.
 * If a corresponding number is found, a numeric interpolator is created using `interpolateNumber`.
 * The remaining parts of the string `b` are used as a template.
 *
 * For example, if `a` is `"300 12px sans-serif"`, and `b` is `"500 36px Comic-Sans"`, two embedded numbers are found.
 * The remaining static parts (of string `b`) are a space between the two numbers (`" "`), and the suffix (`"px Comic-Sans"`).
 * The result of the interpolator at `t` = 0.5 is `"400 24px Comic-Sans"`.
 */
export function interpolateString(
    a: string | { toString(): string },
    b: string | { toString(): string },
): (t: number) => string;

/**
 * Returns an interpolator between the two dates `a` and `b`.
 *
 * Note: *no defensive copy* of the returned date is created; the same Date instance is returned for every evaluation of the interpolator.
 * No copy is made for performance reasons; interpolators are often part of the inner loop of animated transitions.
 */
export function interpolateDate(a: Date, b: Date): (t: number) => Date;

export type ArrayInterpolator<A extends any[]> = (t: number) => A;

/**
 * Returns an interpolator between the two arrays `a` and `b`. Internally, an array template is created that is the same length in `b`.
 * For each element in `b`, if there exists a corresponding element in `a`, a generic interpolator is created for the two elements using `interpolate`.
 * If there is no such element, the static value from `b` is used in the template.
 * Then, for the given parameter `t`, the template’s embedded interpolators are evaluated. The updated array template is then returned.
 *
 * For example, if `a` is the array `[0, 1]` and `b` is the array `[1, 10, 100]`, then the result of the interpolator for `t = 0.5` is the array `[0.5, 5.5, 100]`.
 *
 * Note: *no defensive copy* of the template array is created; modifications of the returned array may adversely affect subsequent evaluation of the interpolator.
 * No copy is made for performance reasons; interpolators are often part of the inner loop of animated transitions.
 */
export function interpolateArray<A extends any[]>(a: any[], b: A): ArrayInterpolator<A>;
/**
 * interpolateNumberArray is called
 */
export function interpolateArray<T extends NumberArray>(a: NumberArray | number[], b: T): (t: number) => T;

/**
 * Returns an interpolator between the two arrays of numbers a and b.
 * Internally, an array template is created that is the same type and length as b.
 * For each element in b, if there exists a corresponding element in a, the values are directly interpolated in the array template.
 * If there is no such element, the static value from b is copied.
 * The updated array template is then returned.
 *
 * Note: For performance reasons, no defensive copy is made of the template array and the arguments a and b; modifications of these arrays may affect subsequent evaluation of the interpolator.
 */
export function interpolateNumberArray<T extends NumberArray | number[]>(
    a: NumberArray | number[],
    b: T,
): (t: number) => T;

/**
 * Returns an interpolator between the two objects `a` and `b`. Internally, an object template is created that has the same properties as `b`.
 * For each property in `b`, if there exists a corresponding property in `a`, a generic interpolator is created for the two elements using `interpolate`.
 * If there is no such property, the static value from `b` is used in the template.
 * Then, for the given parameter `t`, the template's embedded interpolators are evaluated and the updated object template is then returned.
 *
 * For example, if `a` is the object `{x: 0, y: 1}` and `b` is the object `{x: 1, y: 10, z: 100}`, the result of the interpolator for `t = 0.5` is the object `{x: 0.5, y: 5.5, z: 100}`.
 *
 * Note: *no defensive copy* of the template object is created; modifications of the returned object may adversely affect subsequent evaluation of the interpolator.
 * No copy is made for performance reasons; interpolators are often part of the inner loop of animated transitions.
 */
export function interpolateObject<U extends object>(a: any, b: U): (t: number) => U;

/**
 * Returns an interpolator between the two 2D CSS transforms represented by `a` and `b`.
 * Each transform is decomposed to a standard representation of translate, rotate, *x*-skew and scale; these component transformations are then interpolated.
 * This behavior is standardized by CSS: see [matrix decomposition for animation](http://www.w3.org/TR/css3-2d-transforms/#matrix-decomposition).
 */
export function interpolateTransformCss(a: string, b: string): (t: number) => string;

/**
 * Returns an interpolator between the two 2D SVG transforms represented by `a` and `b`.
 * Each transform is decomposed to a standard representation of translate, rotate, *x*-skew and scale; these component transformations are then interpolated.
 * This behavior is standardized by CSS: see [matrix decomposition for animation](http://www.w3.org/TR/css3-2d-transforms/#matrix-decomposition).
 */
export function interpolateTransformSvg(a: string, b: string): (t: number) => string;

/**
 * Returns an interpolator between the two views `a` and `b` of a two-dimensional plane,
 * based on [“Smooth and efficient zooming and panning”](http://www.win.tue.nl/~vanwijk/zoompan.pdf).
 * Each view is defined as an array of three numbers: *cx*, *cy* and *width*.
 * The first two coordinates *cx*, *cy* represent the center of the viewport; the last coordinate *width* represents the size of the viewport.
 *
 * The returned interpolator exposes a *duration* property which encodes the recommended transition duration in milliseconds.
 * This duration is based on the path length of the curved trajectory through *x,y* space.
 * If you want to a slower or faster transition, multiply this by an arbitrary scale factor (*V* as described in the original paper).
 */
export function interpolateZoom(a: ZoomView, b: ZoomView): ZoomInterpolator;

/**
 * Returns a discrete interpolator for the given array of values. The returned interpolator maps `t` in `[0, 1 / n)` to values[0],
 * `t` in `[1 / n, 2 / n)` to `values[1]`, and so on, where `n = values.length`. In effect, this is a lightweight quantize scale with a fixed domain of [0, 1].
 */
export function interpolateDiscrete<T>(values: T[]): (t: number) => T;

// Sampling ------------------------------------------------------------------

/**
 * Returns `n` uniformly-spaced samples from the specified `interpolator`, where `n` is an integer greater than one.
 * The first sample is always at `t = 0`, and the last sample is always at `t = 1`.
 * This can be useful in generating a fixed number of samples from a given interpolator,
 * such as to derive the range of a [quantize scale](https://github.com/d3/d3-scale#quantize-scales) from a [continuous interpolator](https://github.com/d3/d3-scale#interpolateWarm).
 *
 * Caution: this method will not work with interpolators that do not return defensive copies of their output,
 * such as `d3.interpolateArray`, `d3.interpolateDate` and `d3.interpolateObject`. For those interpolators, you must wrap the interpolator and create a copy for each returned value.
 */
export function quantize<T>(interpolator: (t: number) => T, n: number): T[];

// Color Spaces

/**
 * Returns an RGB color space interpolator between the two colors `a` and `b` with a configurable gamma. If the gamma is not specified, it defaults to 1.0.
 * The colors `a` and `b` need not be in RGB; they will be converted to RGB using [`d3.rgb`](https://github.com/d3/d3-color#rgb). The return value of the interpolator is an RGB string.
 */
export const interpolateRgb: ColorGammaInterpolationFactory;

/**
 * Returns a uniform nonrational B-spline interpolator through the specified array of *colors*, which are converted to RGB color space.
 * Implicit control points are generated such that the interpolator returns `colors[0]` at `t = 0` and `colors[colors.length - 1]` at `t = 1`.
 * Opacity interpolation is not currently supported. See also `d3.interpolateBasis`, and see [d3-scale-chromatic](https://github.com/d3/d3-scale-chromatic) for examples.
 */
export function interpolateRgbBasis(colors: Array<string | ColorCommonInstance>): (t: number) => string;

/**
 * Returns a uniform nonrational B-spline interpolator through the specified array of colors, which are converted to RGB color space.
 * The control points are implicitly repeated such that the resulting spline has cyclical C² continuity when repeated around `t` in [0,1];
 * this is useful, for example, to create cyclical color scales. Opacity interpolation is not currently supported.
 * See also `d3.interpolateBasisClosed, and see [d3-scale-chromatic](https://github.com/d3/d3-scale-chromatic) for examples.
 */
export function interpolateRgbBasisClosed(colors: Array<string | ColorCommonInstance>): (t: number) => string;

/**
 * Returns an HSL color space interpolator between the two colors *a* and *b*. The colors *a* and *b* need not be in HSL;
 * they will be converted to HSL using `d3.hsl`. If either color’s hue or saturation is NaN, the opposing color’s channel value is used.
 * The shortest path between hues is used. The return value of the interpolator is an RGB string.
 */
export function interpolateHsl(a: string | ColorCommonInstance, b: string | ColorCommonInstance): (t: number) => string;

/**
 * Like `interpolateHsl`, but does not use the shortest path between hues.
 */
export function interpolateHslLong(
    a: string | ColorCommonInstance,
    b: string | ColorCommonInstance,
): (t: number) => string;

/**
 * Returns a Lab color space interpolator between the two colors *a* and *b*. The colors *a* and *b* need not be in Lab;
 * they will be converted to Lab using `d3.lab`. The return value of the interpolator is an RGB string.
 */
export function interpolateLab(a: string | ColorCommonInstance, b: string | ColorCommonInstance): (t: number) => string;

/**
 * Returns an HCL color space interpolator between the two colors `a` and `b`. The colors `a` and `b` need not be in HCL;
 * they will be converted to HCL using `d3.hcl`. If either color’s hue or chroma is NaN, the opposing color’s channel value is used.
 * The shortest path between hues is used. The return value of the interpolator is an RGB string.
 */
export function interpolateHcl(a: string | ColorCommonInstance, b: string | ColorCommonInstance): (t: number) => string;

/**
 * Like `interpolateHcl`, but does not use the shortest path between hues.
 */
export function interpolateHclLong(
    a: string | ColorCommonInstance,
    b: string | ColorCommonInstance,
): (t: number) => string;

/**
 * Returns a Cubehelix color space interpolator between the two colors `a` and `b` using a configurable `gamma`.
 * If the gamma is not specified, it defaults to 1.0. The colors `a` and `b` need not be in Cubehelix;
 * they will be converted to Cubehelix using [`d3.cubehelix`](https://github.com/d3/d3-color#cubehelix).
 * If either color’s hue or saturation is NaN, the opposing color’s channel value is used. The shortest path between hues is used. The return value of the interpolator is an RGB string.
 */
export const interpolateCubehelix: ColorGammaInterpolationFactory;

/**
 * Like `interpolateCubehelix`, but does not use the shortest path between hues.
 */
export const interpolateCubehelixLong: ColorGammaInterpolationFactory;

/**
 * Returns an interpolator between the two hue angles `a` and `b`. If either hue is NaN, the opposing value is used.
 * The shortest path between hues is used. The return value of the interpolator is a number in `[0, 360)`.
 */
export function interpolateHue(a: number, b: number): (t: number) => number;

// Splines -------------------------------------------------------------------

/**
 * Returns a uniform nonrational B-spline interpolator through the specified array of `values`, which must be numbers.
 * Implicit control points are generated such that the interpolator returns `values[0]` at `t` = 0 and `values[values.length - 1]` at `t` = 1.
 * See also [`d3.curveBasis`](https://github.com/d3/d3-shape#curveBasis).
 */
export function interpolateBasis(splineNodes: number[]): (t: number) => number;

/**
 * Returns a uniform nonrational B-spline interpolator through the specified array of `values`, which must be numbers.
 * The control points are implicitly repeated such that the resulting one-dimensional spline has cyclical C² continuity when repeated around `t` in [0,1].
 * See also [`d3.curveBasisClosed`](https://github.com/d3/d3-shape#curveBasisClosed).
 */
export function interpolateBasisClosed(splineNodes: number[]): (t: number) => number;

// Piecewise -----------------------------------------------------------------

/**
 * Returns a piecewise zoom interpolator, composing zoom interpolators for each adjacent pair of zoom view.
 * The returned interpolator maps `t` in `[0, 1 / (n - 1)]` to `interpolate(values[0], values[1])`, `t` in `[1 / (n - 1), 2 / (n - 1)]` to `interpolate(values[1], values[2])`,
 * and so on, where `n = values.length`. In effect, this is a lightweight linear scale.
 * For example, to blend through three different zoom views: `d3.piecewise(d3.interpolateZoom, [[0, 0, 1], [0, 0, 10], [0, 0, 15]])`.
 *
 * interpolate defaults to d3.interpolate.
 */
export function piecewise(values: ZoomView[]): ZoomInterpolator;
/**
 * Returns a piecewise zoom interpolator, composing zoom interpolators for each adjacent pair of zoom view.
 * The returned interpolator maps `t` in `[0, 1 / (n - 1)]` to `interpolate(values[0], values[1])`, `t` in `[1 / (n - 1), 2 / (n - 1)]` to `interpolate(values[1], values[2])`,
 * and so on, where `n = values.length`. In effect, this is a lightweight linear scale.
 * For example, to blend through three different zoom views: `d3.piecewise(d3.interpolateZoom, [[0, 0, 1], [0, 0, 10], [0, 0, 15]])`.
 */
export function piecewise(
    interpolate: (a: ZoomView, b: ZoomView) => ZoomInterpolator,
    values: ZoomView[],
): ZoomInterpolator;

/**
 * Returns a piecewise array interpolator, composing array interpolators for each adjacent pair of arrays.
 * The returned interpolator maps `t` in `[0, 1 / (n - 1)]` to `interpolate(values[0], values[1])`, `t` in `[1 / (n - 1), 2 / (n - 1)]` to `interpolate(values[1], values[2])`,
 * and so on, where `n = values.length`. In effect, this is a lightweight linear scale.
 * For example, to blend through three different arrays: `d3.piecewise(d3.interpolateArray, [[0, 0, 1], [0, 0, 10], [0, 0, 15]])`.
 *
 * interpolate defaults to d3.interpolate.
 */
export function piecewise<A extends any[]>(values: A[]): ArrayInterpolator<A>;
/**
 * Returns a piecewise array interpolator, composing array interpolators for each adjacent pair of arrays.
 * The returned interpolator maps `t` in `[0, 1 / (n - 1)]` to `interpolate(values[0], values[1])`, `t` in `[1 / (n - 1), 2 / (n - 1)]` to `interpolate(values[1], values[2])`,
 * and so on, where `n = values.length`. In effect, this is a lightweight linear scale.
 * For example, to blend through three different arrays: `d3.piecewise(d3.interpolateArray, [[0, 0, 1], [0, 0, 10], [0, 0, 15]])`.
 */
export function piecewise<A extends any[]>(
    interpolate: (a: any[], b: A) => ArrayInterpolator<A>,
    values: A[],
): ArrayInterpolator<A>;

/**
 * Returns a piecewise interpolator, composing interpolators for each adjacent pair of values.
 * The returned interpolator maps `t` in `[0, 1 / (n - 1)]` to `interpolate(values[0], values[1])`, `t` in `[1 / (n - 1), 2 / (n - 1)]` to `interpolate(values[1], values[2])`,
 * and so on, where `n = values.length`. In effect, this is a lightweight linear scale.
 * For example, to blend through red, green and blue: `d3.piecewise(d3.interpolateRgb.gamma(2.2), ["red", "green", "blue"])`.
 *
 * interpolate defaults to d3.interpolate.
 */
export function piecewise(values: unknown[]): (t: number) => any;
/**
 * Returns a piecewise interpolator, composing interpolators for each adjacent pair of values.
 * The returned interpolator maps `t` in `[0, 1 / (n - 1)]` to `interpolate(values[0], values[1])`, `t` in `[1 / (n - 1), 2 / (n - 1)]` to `interpolate(values[1], values[2])`,
 * and so on, where `n = values.length`. In effect, this is a lightweight linear scale.
 * For example, to blend through red, green and blue: `d3.piecewise(d3.interpolateRgb.gamma(2.2), ["red", "green", "blue"])`.
 */
export function piecewise<TData>(interpolate: (a: TData, b: TData) => unknown, values: TData[]): (t: number) => any;
