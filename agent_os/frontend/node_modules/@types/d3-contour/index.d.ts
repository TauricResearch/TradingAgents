// Last module patch version validated against: 3.0.1

import { ThresholdCountGenerator, ThresholdNumberArrayGenerator } from "d3-array";
import { MultiPolygon } from "geojson";

/**
 * An extended GeoJSON MultiPolygon representing a contour.
 */
export interface ContourMultiPolygon extends MultiPolygon {
    /**
     * Threshold value of the contour.
     */
    value: number;
}

/**
 * A contour generator which computes contour polygons by applying marching squares to a rectangular array of numeric values.
 *
 * For each threshold value, the contour generator constructs a GeoJSON MultiPolygon geometry object representing the area
 * where the input values are greater than or equal to the threshold value.
 * The geometry is in planar coordinates, where ⟨i + 0.5, j + 0.5⟩ corresponds to element i + jn in the input values array.
 */
export interface Contours {
    /**
     * Computes the contours for the given array of values, returning an array of GeoJSON MultiPolygon geometry objects.
     * Each geometry object represents the area where the input values are greater than or equal to the corresponding threshold value;
     * the threshold value for each geometry object is exposed as geometry.value.
     *
     * The returned geometry objects are typically passed to d3.geoPath to display,
     * using null or d3.geoIdentity as the associated projection
     *
     * @param values Array of input values. The input values must be an array of length n×m where [n, m] is the contour generator’s size;
     * furthermore, each values[i + jn] must represent the value at the position ⟨i, j⟩.
     */
    (values: number[]): ContourMultiPolygon[];

    /**
     * Computes a single contour, returning a GeoJSON MultiPolygon geometry object.
     * This geometry object represents the area where the input values are greater than or equal to the given threshold value;
     * the threshold value for the geometry object is exposed as geometry.value.
     *
     * @param values  Array of input values. The input values must be an array of length n×m where [n, m] is the contour generator’s size;
     * furthermore, each values[i + jn] must represent the value at the position ⟨i, j⟩.
     * @param threshold Threshold value.
     */
    contour(values: number[], threshold: number): ContourMultiPolygon;

    /**
     * Return the expected size of the input values grid, which defaults to [1,1].
     */
    size(): [number, number];
    /**
     * Sets the expected size of the input values grid to the contour generator and returns the contour generator.
     *
     * @param size Size of the input values grid specified as an array [n, m]
     * where n is the number of columns in the grid and m is the number of rows; n and m must be positive integers.
     */
    size(size: [number, number]): this;

    /**
     * Returns the current smoothing flag, which defaults to true.
     */
    smooth(): boolean;
    /**
     * Sets whether or not the generated contour polygons are smoothed using linear interpolation and returns the contour generator.
     *
     * @param smooth Flag to enable linear interpolation. The default is "true".
     */
    smooth(smooth: boolean): this;

    /**
     * Returns the current threshold generator, which by default implements Sturges’ formula.
     */
    thresholds(): ThresholdCountGenerator<number> | ThresholdNumberArrayGenerator<number>;
    /**
     * Sets the threshold generator to the specified function or array and returns this contour generator.
     * Thresholds are defined as an array of values [x0, x1, …].
     * The first generated contour corresponds to the area where the input values are greater than or equal to x0;
     * the second contour corresponds to the area where the input values are greater than or equal to x1, and so on.
     * Thus, there is exactly one generated MultiPolygon geometry object for each specified threshold value; the threshold value is exposed as geometry.value.
     * If a count is specified instead of an array of thresholds, then the input values’ extent will be uniformly divided into approximately count bins; see d3.ticks.
     */
    thresholds(
        thresholds: number | number[] | ThresholdCountGenerator<number> | ThresholdNumberArrayGenerator<number>,
    ): this;
}

/**
 * Construct a new contour generator with the default settings.
 */
export function contours(): Contours;

/**
 * A contour generator for density estimates.
 *
 * The generic refers to the data type of an element in the data array
 * used with the density contour generator. If omitted, the default setting assumes that,
 * the elements of the data array used with the density contour generator are two-element arrays.
 * The first element corresponds to the x-dimension, the second to the y-dimension.
 */
export interface ContourDensity<Datum = [number, number]> {
    /**
     * Estimates the density contours for the given array of data, returning an array of GeoJSON MultiPolygon geometry objects.
     * Each geometry object represents the area where the estimated number of points per square pixel is greater than or equal to
     * the corresponding threshold value; the threshold value for each geometry object is exposed as geometry.value.
     * The returned geometry objects are typically passed to d3.geoPath to display, using null or d3.geoIdentity as the associated projection.
     * See also d3.contours.
     *
     * The x- and y-coordinate for each data point are computed using density.x and density.y.
     * The generated contours are only accurate within the estimator’s defined size.
     *
     * @param data Array of input data.
     */
    (data: Datum[]): ContourMultiPolygon[];

    /**
     * Returns the current x-coordinate accessor.
     * The default x-coordinate accessor is a functions which accepts as input a two-element array of numbers
     * and returns the element at index 0.
     */
    x(): (d: Datum) => number;
    /**
     * Sets the x-coordinate accessor and returns the density contour estimator.
     *
     * @param x An x-coordinate accessor function, which accepts as input an element of the input data array and returns the
     * x-coordinate.
     */
    x(x: (d: Datum) => number): this;

    /**
     * Returns the current y-coordinate accessor.
     * The default y-coordinate accessor is a functions which accepts as input a two-element array of numbers
     * and returns the element at index 1.
     */
    y(): (d: Datum) => number;
    /**
     * Sets the y-coordinate accessor and returns the density contour estimator.
     *
     * @param y An y-coordinate accessor function, which accepts as input an element of the input data array and returns the
     * y-coordinate.
     */
    y(y: (d: Datum) => number): this;

    /**
     * Returns the current point weight accessor.
     */
    weight(): (d: Datum) => number;

    /**
     * Sets the point weight accessor and returns the density contour estimator.
     *
     * @param weight A point weight accessor function.
     */
    weight(weight: (d: Datum) => number): this;

    /**
     * Returns the current size, which defaults to [960, 500].
     */
    size(): [number, number];
    /**
     * Sets the size of the density estimator to the specified bounds and returns the density contour estimator.
     *
     * @param size The size is specified as an array [width, height], where width is the maximum x-value and height is the maximum y-value.
     */
    size(size: [number, number]): this;

    /**
     * Returns the current cell size, which defaults to 4.
     */
    cellSize(): number;
    /**
     * Sets the size of individual cells in the underlying bin grid to the specified positive integer and returns the density contour estimator.
     *
     * The cell size is rounded down to the nearest power of two. Smaller cells produce more detailed contour polygons, but are more expensive to compute.
     *
     * @param cellSize Cell size, a positive integer.
     */
    cellSize(cellSize: number): this;

    /**
     * Returns the current threshold generator, which by default generates about twenty nicely-rounded density thresholds.
     */
    thresholds(): ThresholdCountGenerator<number> | ThresholdNumberArrayGenerator<number>;
    /**
     * Sets the threshold generator to the specified function or array and returns this contour generator.
     * Thresholds are defined as an array of values [x0, x1, …].
     * The first generated density contour corresponds to the area where the estimated density is greater than or equal to x0;
     * the second contour corresponds to the area where the estimated density is greater than or equal to x1, and so on.
     * Thus, there is exactly one generated MultiPolygon geometry object for each specified threshold value; the threshold value is exposed as geometry.value.
     * The first value x0 should typically be greater than zero.
     * If a count is specified instead of an array of thresholds, then approximately count uniformly-spaced nicely-rounded thresholds will be generated; see d3.ticks.
     */
    thresholds(
        thresholds: number | number[] | ThresholdCountGenerator<number> | ThresholdNumberArrayGenerator<number>,
    ): this;

    /**
     * Returns the current bandwidth, which defaults to 20.4939….
     */
    bandwidth(): number;
    /**
     * Sets the bandwidth (the standard deviation) of the Gaussian kernel and returns the density contour estimator.
     *
     * @param bandwidth Bandwidth (the standard deviation) of the Gaussian kernel.
     * The specified bandwidth is currently rounded to the nearest supported value by this implementation, and must be nonnegative.
     */
    bandwidth(bandwidth: number): this;
}

/**
 * Construct a new contour generator for density estimates.
 *
 * The generic refers to the data type of an element in the data array
 * used with the density contour generator. If omitted, the default setting assumes that,
 * the elements of the data array used with the density contour generator are two-element arrays.
 * The first element corresponds to the x-dimension, the second to the y-dimension.
 *
 * Important: ensure that the x- and y-accessor functions are configured to
 * match the data type used for the generic Datum.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function contourDensity<Datum = [number, number]>(): ContourDensity<Datum>;
