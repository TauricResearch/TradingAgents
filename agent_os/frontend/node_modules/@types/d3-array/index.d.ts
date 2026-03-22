// Last module patch version validated against: 3.2.4

// --------------------------------------------------------------------------
// Shared Types and Interfaces
// --------------------------------------------------------------------------

/**
 * Administrivia: JavaScript primitive types and Date
 */
export type Primitive = number | string | boolean | Date;

/**
 * Administrivia: anything with a valueOf(): number method is comparable, so we allow it in numeric operations
 */
export interface Numeric {
    valueOf(): number;
}

/**
 * Administrivia: a matrix of numeric values.
 * If height is not specified, it is inferred from the given width and data.length.
 */
export interface Matrix {
    data: ArrayLike<number>;
    width: number;
    height?: number;
}

/**
 * Represents a nested/recursive InternMap type
 *
 * The first generic "TObject" refers to the type of the data object that is available in the accessor functions.
 * The second generic "TReduce" refers to the type of the data available at the deepest level (the result data).
 * The third generic "TKeys" refers to the type of the keys at each level of the nestes InternMap.
 */
export type NestedInternMap<TObject, TReduce, TKeys extends unknown[]> = TKeys extends [infer TFirst, ...infer TRest]
    ? InternMap<TFirst, NestedInternMap<TObject, TReduce, TRest>>
    : TReduce;

/**
 * Represents a nested/recursive Array type
 *
 * The first generic "TObject" refers to the type of the data object that is available in the accessor functions.
 * The second generic "TReduce" refers to the type of the data available at the deepest level (the result data).
 * The third generic "TKeys" refers to the type of the keys at each level of the nestes Array.
 */
export type NestedArray<TObject, TReduce, TKeys extends unknown[]> = TKeys extends [infer TFirst, ...infer TRest]
    ? Array<[TFirst, NestedArray<TObject, TReduce, TRest>]>
    : TReduce;

// --------------------------------------------------------------------------------------
// Statistics
// --------------------------------------------------------------------------------------

/**
 * Return the minimum value in the array using natural order.
 */
export function min(iterable: Iterable<string>): string | undefined;

/**
 * Return the minimum value in the array using natural order.
 */
export function min<T extends Numeric>(iterable: Iterable<T>): T | undefined;
/**
 * Return the minimum value in the array using natural order.
 */
export function min<T>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => string | undefined | null,
): string | undefined;
/**
 * Return the minimum value in the array using natural order.
 */
export function min<T, U extends Numeric>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => U | undefined | null,
): U | undefined;

/**
 * Return the index of the minimum value in the array using natural order.
 */
export function minIndex(iterable: Iterable<unknown>): number;
/**
 * Return the index of the minimum value in the array using natural order and a projection function to map values.
 */
export function minIndex<TDatum>(
    iterable: Iterable<TDatum>,
    accessor: (datum: TDatum, index: number, array: Iterable<TDatum>) => unknown,
): number;
/**
 * Return the index of the minimum value in the array using natural order.
 */
export function minIndex(iterable: Iterable<unknown>): number;

/**
 * Return the maximum value in the array of strings using natural order.
 */
export function max(iterable: Iterable<string>): string | undefined;
/**
 * Return the maximum value in the array of numbers using natural order.
 */
export function max<T extends Numeric>(iterable: Iterable<T>): T | undefined;
/**
 * Return the maximum value in the array using natural order and a projection function to map values to strings.
 */
export function max<T>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => string | undefined | null,
): string | undefined;
/**
 * Return the maximum value in the array using natural order and a projection function to map values to easily-sorted values.
 */
export function max<T, U extends Numeric>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => U | undefined | null,
): U | undefined;

/**
 * Return the index of the maximum value in the array using natural order.
 */
export function maxIndex(iterable: Iterable<unknown>): number;
/**
 * Return the index of the maximum value in the array using natural order and a projection function to map values.
 */
export function maxIndex<TDatum>(
    iterable: Iterable<TDatum>,
    accessor: (datum: TDatum, index: number, array: Iterable<TDatum>) => unknown,
): number;

/**
 * Return the min and max simultaneously.
 */
export function extent(iterable: Iterable<string>): [string, string] | [undefined, undefined];
/**
 * Return the min and max simultaneously.
 */
export function extent<T extends Numeric>(iterable: Iterable<T>): [T, T] | [undefined, undefined];
/**
 * Return the min and max simultaneously.
 */
export function extent<T>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => string | undefined | null,
): [string, string] | [undefined, undefined];
/**
 * Return the min and max simultaneously.
 */
export function extent<T, U extends Numeric>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => U | undefined | null,
): [U, U] | [undefined, undefined];

/**
 * Returns the mode of the given iterable, i.e. the value which appears the most often.
 * In case of equality, returns the first of the relevant values.
 * If the iterable contains no comparable values, returns undefined.
 * An optional accessor function may be specified, which is equivalent to calling Array.from before computing the mode.
 * This method ignores undefined, null and NaN values; this is useful for ignoring missing data.
 */
export function mode(iterable: Iterable<Numeric | undefined | null>): number;
/**
 * Returns the mode of the given iterable, i.e. the value which appears the most often.
 * In case of equality, returns the first of the relevant values.
 * If the iterable contains no comparable values, returns undefined.
 * An optional accessor function may be specified, which is equivalent to calling Array.from before computing the mode.
 * This method ignores undefined, null and NaN values; this is useful for ignoring missing data.
 */
export function mode<T>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => number | undefined | null,
): number;

/**
 * Compute the sum of an array of numbers.
 */
export function sum(iterable: Iterable<Numeric | undefined | null>): number;
/**
 * Compute the sum of an array, using the given accessor to convert values to numbers.
 */
export function sum<T>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => number | undefined | null,
): number;

/**
 * Return the mean of an array of numbers
 */
export function mean(iterable: Iterable<Numeric | undefined | null>): number | undefined;
/**
 * Return the mean of an array of numbers
 */
export function mean<T>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => number | undefined | null,
): number | undefined;

/**
 * Return the median of an array of numbers
 */
export function median(iterable: Iterable<Numeric | undefined | null>): number | undefined;
/**
 * Return the median of an array of numbers
 */
export function median<T>(
    iterable: Iterable<T>,
    accessor: (element: T, i: number, array: Iterable<T>) => number | undefined | null,
): number | undefined;

/**
 * Like median, but returns the index of the element to the left of the median.
 */
export function medianIndex(iterable: Iterable<Numeric | undefined | null>): number;
/**
 * Like median, but returns the index of the element to the left of the median.
 */
export function medianIndex<T>(
    iterable: Iterable<T>,
    accessor: (element: T, i: number, array: Iterable<T>) => number | undefined | null,
): number;

/**
 * Returns the cumulative sum of the given iterable of numbers, as a Float64Array of the same length.
 * If the iterable contains no numbers, returns zeros.
 * An optional accessor function may be specified, which is equivalent to calling Array.from before computing the cumulative sum.
 * This method ignores undefined and NaN values; this is useful for ignoring missing data.
 */
export function cumsum(iterable: Iterable<Numeric | undefined | null>): Float64Array;
/**
 * Returns the cumulative sum of the given iterable of numbers, as a Float64Array of the same length.
 * If the iterable contains no numbers, returns zeros.
 * An optional accessor function may be specified, which is equivalent to calling Array.from before computing the cumulative sum.
 * This method ignores undefined and NaN values; this is useful for ignoring missing data.
 */
export function cumsum<T>(
    iterable: Iterable<T>,
    accessor: (element: T, i: number, array: Iterable<T>) => number | undefined | null,
): Float64Array;

/**
 * Returns the p-quantile of the given iterable of numbers, where p is a number in the range [0, 1].
 *
 * An optional accessor function may be specified, which is equivalent to calling array.map(accessor) before computing the quantile.
 */
export function quantile(iterable: Iterable<Numeric | undefined | null>, p: number): number | undefined;
/**
 * Returns the p-quantile of the given iterable of numbers, where p is a number in the range [0, 1].
 *
 * An optional accessor function may be specified, which is equivalent to calling array.map(accessor) before computing the quantile.
 */
export function quantile<T>(
    iterable: Iterable<T>,
    p: number,
    accessor: (element: T, i: number, array: Iterable<T>) => number | undefined | null,
): number | undefined;

/**
 * Similar to quantile, but returns the index to the left of p.
 */
export function quantileIndex(iterable: Iterable<Numeric | undefined | null>, p: number): number;
/**
 * Similar to quantile, but returns the index to the left of p.
 */
export function quantileIndex<T>(
    iterable: Iterable<T>,
    p: number,
    accessor: (element: T, i: number, array: Iterable<T>) => number | undefined | null,
): number;

/**
 * Similar to quantile, but expects the input to be a sorted array of values.
 * In contrast with quantile, the accessor is only called on the elements needed to compute the quantile.
 */
export function quantileSorted(
    array: Array<Numeric | undefined | null>,
    p: number,
): number | undefined;
/**
 * Similar to quantile, but expects the input to be a sorted array of values.
 * In contrast with quantile, the accessor is only called on the elements needed to compute the quantile.
 */
export function quantileSorted<T>(
    array: T[],
    p: number,
    accessor: (element: T, i: number, array: T[]) => number | undefined | null,
): number | undefined;

/**
 * Returns an array with the rank of each value in the iterable, i.e. the zero-based index of the value when the iterable is sorted.
 * Nullish values are sorted to the end and ranked NaN.
 * An optional comparator or accessor function may be specified; the latter is equivalent to calling array.map(accessor) before computing the ranks.
 * If comparator is not specified, it defaults to ascending.
 * Ties (equivalent values) all get the same rank, defined as the first time the value is found.
 */
export function rank(iterable: Iterable<Numeric | undefined | null>): Float64Array;
/**
 * Returns an array with the rank of each value in the iterable, i.e. the zero-based index of the value when the iterable is sorted.
 * Nullish values are sorted to the end and ranked NaN.
 * An optional comparator or accessor function may be specified; the latter is equivalent to calling array.map(accessor) before computing the ranks.
 * If comparator is not specified, it defaults to ascending.
 * Ties (equivalent values) all get the same rank, defined as the first time the value is found.
 */
export function rank<T>(
    iterable: Iterable<T>,
    accessorOrComparator:
        | ((datum: T, index: number, array: Iterable<T>) => number | undefined | null)
        | ((a: T, b: T) => number | undefined | null),
): Float64Array;

/**
 * Returns an unbiased estimator of the population variance of the given iterable of numbers using Welford’s algorithm.
 * If the iterable has fewer than two numbers, returns undefined.
 * An optional accessor function may be specified, which is equivalent to calling Array.from before computing the variance.
 * This method ignores undefined and NaN values; this is useful for ignoring missing data.
 */
export function variance(iterable: Iterable<Numeric | undefined | null>): number | undefined;
/**
 * Returns an unbiased estimator of the population variance of the given iterable of numbers using Welford’s algorithm.
 * If the iterable has fewer than two numbers, returns undefined.
 * An optional accessor function may be specified, which is equivalent to calling Array.from before computing the variance.
 * This method ignores undefined and NaN values; this is useful for ignoring missing data.
 */
export function variance<T>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => number | undefined | null,
): number | undefined;

/**
 * Compute the standard deviation, defined as the square root of the bias-corrected variance, of the given array of numbers.
 */
export function deviation(iterable: Iterable<Numeric | undefined | null>): number | undefined;
/**
 * Compute the standard deviation, defined as the square root of the bias-corrected variance, of the given array,
 * using the given accessor to convert values to numbers.
 */
export function deviation<T>(
    iterable: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => number | undefined | null,
): number | undefined;

/**
 * Returns a full precision summation of the given values.
 * Although slower, d3.fsum can replace d3.sum wherever greater precision is needed. Uses d3.Adder.
 */
export function fsum(values: Iterable<Numeric | undefined | null>): number;
/**
 * Returns a full precision summation of the given values.
 * Although slower, d3.fsum can replace d3.sum wherever greater precision is needed. Uses d3.Adder.
 */
export function fsum<T>(
    values: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => number | undefined | null,
): number;

/**
 * Returns a full precision cumulative sum of the given values.
 * Although slower, d3.fcumsum can replace d3.cumsum when greater precision is needed. Uses d3.Adder.
 */
export function fcumsum(values: Iterable<Numeric | undefined | null>): Float64Array;
/**
 * Returns a full precision cumulative sum of the given values.
 * Although slower, d3.fcumsum can replace d3.cumsum when greater precision is needed. Uses d3.Adder.
 */
export function fcumsum<T>(
    values: Iterable<T>,
    accessor: (datum: T, index: number, array: Iterable<T>) => number | undefined | null,
): Float64Array;

export class Adder {
    /**
     * Creates a full precision adder for IEEE 754 floating point numbers, setting its initial value to 0.
     */
    constructor();

    /**
     * Adds the specified number to the adder’s current value and returns the adder.
     */
    add(number: number): Adder;

    /**
     * Returns the IEEE 754 double precision representation of the adder’s current value.
     * Most useful as the short-hand notation +adder.
     */
    valueOf(): number;
}

// --------------------------------------------------------------------------------------
// Search
// --------------------------------------------------------------------------------------

/**
 * Returns the least element of the specified iterable according to the specified comparator.
 * If comparator is not specified, it defaults to ascending.
 */
export function least<T>(iterable: Iterable<T>, comparator?: (a: T, b: T) => number): T | undefined;
/**
 * Returns the least element of the specified iterable according to the specified accessor.
 */
export function least<T>(iterable: Iterable<T>, accessor: (a: T) => unknown): T | undefined;

/**
 * Returns the index of the least element of the specified iterable according to the specified comparator.
 */
export function leastIndex(iterable: Iterable<unknown>): number | undefined;
/**
 * Returns the index of the least element of the specified iterable according to the specified comparator.
 */
export function leastIndex<T>(iterable: Iterable<T>, comparator: (a: T, b: T) => number): number | undefined;
/**
 * Returns the index of the least element of the specified iterable according to the specified accessor.
 */
// tslint:disable-next-line:unified-signatures
export function leastIndex<T>(iterable: Iterable<T>, accessor: (a: T) => unknown): number | undefined;

/**
 * Returns the greatest element of the specified iterable according to the specified comparator or accessor.
 * If the given iterable contains no comparable elements (i.e., the comparator returns NaN when comparing each element to itself), returns undefined.
 * If comparator is not specified, it defaults to ascending.
 */
export function greatest<T>(iterable: Iterable<T>, comparator?: (a: T, b: T) => number): T | undefined;
/**
 * Returns the greatest element of the specified iterable according to the specified comparator or accessor.
 * If the given iterable contains no comparable elements (i.e., the comparator returns NaN when comparing each element to itself), returns undefined.
 * If comparator is not specified, it defaults to ascending.
 */
export function greatest<T>(iterable: Iterable<T>, accessor: (a: T) => unknown): T | undefined;

/**
 * Returns the index of the greatest element of the specified iterable according to the specified comparator or accessor.
 * If the given iterable contains no comparable elements (i.e., the comparator returns NaN when comparing each element to itself), returns -1.
 * If comparator is not specified, it defaults to ascending.
 */
export function greatestIndex(iterable: Iterable<unknown>): number | undefined;
/**
 * Returns the index of the greatest element of the specified iterable according to the specified comparator or accessor.
 * If the given iterable contains no comparable elements (i.e., the comparator returns NaN when comparing each element to itself), returns -1.
 * If comparator is not specified, it defaults to ascending.
 */
export function greatestIndex<T>(iterable: Iterable<T>, comparator: (a: T, b: T) => number): number | undefined;
/**
 * Returns the index of the greatest element of the specified iterable according to the specified comparator or accessor.
 * If the given iterable contains no comparable elements (i.e., the comparator returns NaN when comparing each element to itself), returns -1.
 * If comparator is not specified, it defaults to ascending.
 */
// tslint:disable-next-line:unified-signatures
export function greatestIndex<T>(iterable: Iterable<T>, accessor: (a: T) => unknown): number | undefined;

export function bisectLeft(array: ArrayLike<number>, x: number, lo?: number, hi?: number): number;
export function bisectLeft(array: ArrayLike<string>, x: string, lo?: number, hi?: number): number;
export function bisectLeft(array: ArrayLike<Date>, x: Date, lo?: number, hi?: number): number;

export function bisectRight(array: ArrayLike<number>, x: number, lo?: number, hi?: number): number;
export function bisectRight(array: ArrayLike<string>, x: string, lo?: number, hi?: number): number;
export function bisectRight(array: ArrayLike<Date>, x: Date, lo?: number, hi?: number): number;

export function bisectCenter(array: ArrayLike<number>, x: number, lo?: number, hi?: number): number;
export function bisectCenter(array: ArrayLike<string>, x: string, lo?: number, hi?: number): number;
export function bisectCenter(array: ArrayLike<Date>, x: Date, lo?: number, hi?: number): number;

export const bisect: typeof bisectRight;

export interface Bisector<T, U> {
    left(array: ArrayLike<T>, x: U, lo?: number, hi?: number): number;
    right(array: ArrayLike<T>, x: U, lo?: number, hi?: number): number;
    center(array: ArrayLike<T>, x: U, lo?: number, hi?: number): number;
}

export function bisector<T, U>(comparator: (a: T, b: U) => number): Bisector<T, U>;
// tslint:disable-next-line:unified-signatures
export function bisector<T, U>(accessor: (x: T) => U): Bisector<T, U>;

/**
 * Rearranges items so that all items in the [left, k] are the smallest. The k-th element will have the (k - left + 1)-th smallest value in [left, right].
 *
 * @param array The array to partially sort (in place).
 * @param k The middle index for partial sorting.
 * @param left The left index of the range to sort.
 * @param right The right index.
 * @param compare The compare function.
 */
export function quickselect<T>(
    array: ArrayLike<T>,
    k: number,
    left?: number,
    right?: number,
    compare?: (a: Primitive | undefined, b: Primitive | undefined) => number,
): T[];

// NB. this is limited to primitive values due to D3's use of the <, >, and >= operators. Results get weird for object instances.
/**
 * Compares two primitive values for sorting (in ascending order).
 */
export function ascending(a: Primitive | undefined, b: Primitive | undefined): number;

// NB. this is limited to primitive values due to D3's use of the <, >, and >= operators. Results get weird for object instances.
/**
 * Compares two primitive values for sorting (in descending order).
 */
export function descending(a: Primitive | undefined, b: Primitive | undefined): number;

// --------------------------------------------------------------------------------------
// Transformations
// --------------------------------------------------------------------------------------

/**
 * Groups the specified iterable of values into an InternMap from key to array of value.
 *
 * @param iterable The iterable to group.
 * @param keys The key functions.
 */
export function group<TObject, TKeys extends unknown[]>(
    iterable: Iterable<TObject>,
    ...keys: {
        [Index in keyof TKeys]: (value: TObject, index: number, values: TObject[]) => TKeys[Index];
    }
): NestedInternMap<TObject, TObject[], TKeys>;

/**
 * Equivalent to group, but returns nested arrays instead of nested maps.
 *
 * @param iterable The iterable to group.
 * @param keys The key functions.
 */
export function groups<TObject, TKeys extends unknown[]>(
    iterable: Iterable<TObject>,
    ...keys: {
        [Index in keyof TKeys]: (value: TObject, index: number, values: TObject[]) => TKeys[Index];
    }
): NestedArray<TObject, TObject[], TKeys>;

/**
 * Equivalent to group, but returns a flat array of [key0, key1, …, values] instead of nested maps.
 *
 * @param iterable The iterable to group.
 * @param keys The key functions.
 */
export function flatGroup<TObject, TKeys extends unknown[]>(
    iterable: Iterable<TObject>,
    ...keys: {
        [Index in keyof TKeys]: (value: TObject, index: number, values: TObject[]) => TKeys[Index];
    }
): Array<[...TKeys, TObject[]]>;

/**
 * Equivalent to group but returns a unique value per compound key instead of an array, throwing if the key is not unique.
 *
 * @param iterable The iterable to group.
 * @param key The key functions.
 */
export function index<TObject, TKeys extends unknown[]>(
    iterable: Iterable<TObject>,
    ...keys: {
        [Index in keyof TKeys]: (value: TObject, index: number, values: TObject[]) => TKeys[Index];
    }
): NestedInternMap<TObject, TObject, TKeys>;

/**
 * Equivalent to index, but returns nested arrays instead of nested maps.
 *
 * @param iterable The iterable to group.
 * @param keys The key functions.
 */
export function indexes<TObject, TKeys extends unknown[]>(
    iterable: Iterable<TObject>,
    ...keys: {
        [Index in keyof TKeys]: (value: TObject, index: number, values: TObject[]) => TKeys[Index];
    }
): NestedArray<TObject, TObject, TKeys>;

/**
 * Groups and reduces the specified array of values into an InternMap from key to value.
 *
 * @param iterable The iterable to group.
 * @param reduce The reduce function.
 * @param keys The key functions.
 */
export function rollup<TObject, TReduce, TKeys extends unknown[]>(
    iterable: Iterable<TObject>,
    reduce: (values: TObject[]) => TReduce,
    ...keys: {
        [Index in keyof TKeys]: (value: TObject, index: number, values: TObject[]) => TKeys[Index];
    }
): NestedInternMap<TObject, TReduce, TKeys>;

/**
 * Equivalent to rollup, but returns nested arrays instead of nested maps.
 *
 * @param iterable The iterable to group.
 * @param reduce The reduce function.
 * @param keys The key functions.
 */
export function rollups<TObject, TReduce, TKeys extends unknown[]>(
    iterable: Iterable<TObject>,
    reduce: (values: TObject[]) => TReduce,
    ...keys: {
        [Index in keyof TKeys]: (value: TObject, index: number, values: TObject[]) => TKeys[Index];
    }
): NestedArray<TObject, TReduce, TKeys>;

/**
 * Equivalent to rollup, but returns a flat array of [key0, key1, …, value] instead of nested maps.
 *
 * @param iterable The iterable to group.
 * @param reduce The reduce function.
 * @param keys The key functions.
 */
export function flatRollup<TObject, TReduce, TKeys extends unknown[]>(
    iterable: Iterable<TObject>,
    reduce: (values: TObject[]) => TReduce,
    ...keys: {
        [Index in keyof TKeys]: (value: TObject, index: number, values: TObject[]) => TKeys[Index];
    }
): Array<[...TKeys, TReduce]>;

/**
 * Groups the specified iterable of elements according to the specified key function, sorts the groups according to the specified comparator, and then returns an array of keys in sorted order.
 * The comparator will be asked to compare two groups a and b and should return a negative value if a should be before b, a positive value if a should be after b, or zero for a partial ordering.
 */
export function groupSort<TObject, TKey>(
    iterable: Iterable<TObject>,
    comparator: (a: TObject[], b: TObject[]) => number,
    key: (value: TObject) => TKey,
): TKey[];
/**
 * Groups the specified iterable of elements according to the specified key function, sorts the groups according to the specified accessor, and then returns an array of keys in sorted order.
 */
export function groupSort<TObject, TKey>(
    iterable: Iterable<TObject>,
    // tslint:disable-next-line:unified-signatures
    accessor: (value: TObject[]) => unknown,
    key: (value: TObject) => TKey,
): TKey[];

/**
 * Returns the number of valid number values (i.e., not null, NaN, or undefined) in the specified iterable; accepts an accessor.
 *
 * @param iterable Input array.
 */
export function count(iterable: Iterable<unknown>): number;
/**
 * Returns the number of valid number values (i.e., not null, NaN, or undefined) in the specified iterable; accepts an accessor.
 *
 * @param iterable Input array.
 * @param accessor Accessor method.
 */
export function count<TObject>(
    iterable: Iterable<TObject>,
    accessor: (a: TObject, b: TObject) => number | null | undefined,
): number;

/**
 * Computes the Cartesian product of any number of iterables.
 *
 * When called **without** a reducer, the result is an array of tuples,
 * where each tuple contains one element from each input iterable.
 *
 * @typeParam T - A tuple type describing the element type of each iterable argument.
 *                For example, passing `[number[], string[]]` infers `T` as `[number, string]`.
 *
 * @param iterables - Two or more iterables to combine into a Cartesian product.
 * @returns An array of tuples containing one value from each iterable.
 *
 * @example
 * ```ts
 * const nums = [1, 2];
 * const chars = ['a', 'b'];
 * const out = cross(nums, chars);
 * //    ^? type: [number, string][]
 * // Example value: [[1,'a'], [1,'b'], [2,'a'], [2,'b']]
 * ```
 */
export function cross<T extends unknown[]>(
    ...iterables: { [K in keyof T]: Iterable<T[K]> }
): T[];

/**
 * Computes the Cartesian product of any number of iterables and then applies
 * a reducer to each tuple, returning the reduced values.
 *
 * The final argument **must** be the reducer function; all prior arguments are iterables.
 *
 * @typeParam T - A tuple type describing the element type of each iterable argument.
 * @typeParam U - The result type produced by the reducer.
 *
 * @param args - The iterables to combine, followed by a reducer function.
 * @param args.reducer - A function invoked with one element from each iterable
 *                       (spread as individual parameters) that returns a reduced value.
 * @returns An array of reduced values returned by the reducer.
 *
 * @example
 * ```ts
 * const nums = [1, 2];
 * const chars = ['a', 'b'];
 * const out = cross(nums, chars, (n, c) => `${n}${c}`);
 * //    ^? type: string[]
 * // Example value: ['1a', '1b', '2a', '2b']
 * ```
 */
export function cross<T extends unknown[], U>(
    ...args: [...iterables: { [K in keyof T]: Iterable<T[K]> }, reducer: (...values: T) => U]
): U[];

/**
 * Merges the specified arrays into a single array.
 */
export function merge<T>(iterables: Iterable<Iterable<T>>): T[];

/**
 * For each adjacent pair of elements in the specified array, returns a new array of tuples of elements i and i - 1.
 * Returns the empty array if the input array has fewer than two elements.
 *
 * @param iterable Array of input elements
 */
export function pairs<T>(iterable: Iterable<T>): Array<[T, T]>;
/**
 * For each adjacent pair of elements in the specified array, in order, invokes the specified reducer function passing the element i and element i - 1.
 * Returns the resulting array of pair-wise reduced elements.
 * Returns the empty array if the input array has fewer than two elements.
 *
 * @param iterable Array of input elements
 * @param reducer A reducer function taking as input to adjacent elements of the input array and returning a reduced value.
 */
export function pairs<T, U>(iterable: Iterable<T>, reducer: (a: T, b: T) => U): U[];

/**
 * Returns a permutation of the specified source object (or array) using the specified iterable of keys.
 * The returned array contains the corresponding property of the source object for each key in keys, in order.
 * For example, `permute(["a", "b", "c"], [1, 2, 0]) // ["b", "c", "a"]`
 *
 * It is acceptable to have more keys than source elements, and for keys to be duplicated or omitted.
 */
export function permute<T>(source: { [key: number]: T }, keys: Iterable<number>): T[];
/**
 * Extract the values from an object into an array with a stable order. For example:
 * `var object = {yield: 27, year: 1931, site: "University Farm"};`
 * `d3.permute(object, ["site", "yield"]); // ["University Farm", 27]`
 */
export function permute<T, K extends keyof T>(source: T, keys: Iterable<K>): Array<T[K]>;

/**
 * Randomizes the order of the specified array using the Fisher–Yates shuffle.
 */
export function shuffle<T>(array: T[], lo?: number, hi?: number): T[];
export function shuffle(array: Int8Array, lo?: number, hi?: number): Int8Array;
export function shuffle(array: Uint8Array, lo?: number, hi?: number): Uint8Array;
export function shuffle(array: Uint8ClampedArray, lo?: number, hi?: number): Uint8ClampedArray;
export function shuffle(array: Int16Array, lo?: number, hi?: number): Int16Array;
export function shuffle(array: Uint16Array, lo?: number, hi?: number): Uint16Array;
export function shuffle(array: Int32Array, lo?: number, hi?: number): Int32Array;
export function shuffle(array: Uint32Array, lo?: number, hi?: number): Uint32Array;
export function shuffle(array: Float32Array, lo?: number, hi?: number): Float32Array;
export function shuffle(array: Float64Array, lo?: number, hi?: number): Float64Array;

/**
 * Returns a shuffle function given the specified random source.
 */
export function shuffler(random: () => number): typeof shuffle;

/**
 * Generate an array of approximately count + 1 uniformly-spaced, nicely-rounded values between start and stop (inclusive).
 * Each value is a power of ten multiplied by 1, 2 or 5. See also d3.tickIncrement, d3.tickStep and linear.ticks.
 *
 * Ticks are inclusive in the sense that they may include the specified start and stop values if (and only if) they are exact,
 * nicely-rounded values consistent with the inferred step. More formally, each returned tick t satisfies start ≤ t and t ≤ stop.
 *
 * @param start Start value for ticks
 * @param stop Stop value for ticks
 * @param count count + 1 is the approximate number of ticks to be returned by d3.ticks.
 */
export function ticks(start: number, stop: number, count: number): number[];

/**
 * Returns the difference between adjacent tick values if the same arguments were passed to d3.ticks:
 * a nicely-rounded value that is a power of ten multiplied by 1, 2 or 5.
 *
 * Like d3.tickStep, except requires that start is always less than or equal to stop, and if the tick step for the given start,
 * stop and count would be less than one, returns the negative inverse tick step instead.
 *
 * This method is always guaranteed to return an integer, and is used by d3.ticks to avoid guarantee that the returned tick values
 * are represented as precisely as possible in IEEE 754 floating point.
 *
 * @param start Start value for ticks
 * @param stop Stop value for ticks
 * @param count count + 1 is the approximate number of ticks to be returned by d3.ticks.
 */
export function tickIncrement(start: number, stop: number, count: number): number;

/**
 * Returns the difference between adjacent tick values if the same arguments were passed to d3.ticks:
 * a nicely-rounded value that is a power of ten multiplied by 1, 2 or 5.
 *
 * Note that due to the limited precision of IEEE 754 floating point, the returned value may not be exact decimals;
 * use d3-format to format numbers for human consumption.
 *
 * @param start Start value for ticks
 * @param stop Stop value for ticks
 * @param count count + 1 is the approximate number of ticks to be returned by d3.ticks.
 */
export function tickStep(start: number, stop: number, count: number): number;

/**
 * Returns a new interval [niceStart, niceStop] covering the given interval [start, stop] and where niceStart and niceStop are guaranteed to align with the corresponding tick step.
 * Like d3.tickIncrement, this requires that start is less than or equal to stop.
 *
 * @param start Start value for ticks
 * @param stop Stop value for ticks
 * @param count count + 1 is the approximate number of ticks to be returned by d3.ticks.
 */
export function nice(start: number, stop: number, count: number): [number, number];

/**
 * Generates a 0-based numeric sequence. The output range does not include 'stop'.
 */
export function range(stop: number): number[];
/**
 * Generates a numeric sequence starting from the given start and stop values. 'step' defaults to 1. The output range does not include 'stop'.
 */
// tslint:disable-next-line:unified-signatures
export function range(start: number, stop: number, step?: number): number[];

/**
 * Transpose a matrix provided in Array of Arrays format.
 */
export function transpose<T>(matrix: ArrayLike<ArrayLike<T>>): T[][];

/**
 * Returns an array of arrays, where the ith array contains the ith element from each of the argument arrays.
 * The returned array is truncated in length to the shortest array in arrays. If arrays contains only a single array, the returned array
 * contains one-element arrays. With no arguments, the returned array is empty.
 */
export function zip<T>(...arrays: Array<ArrayLike<T>>): T[][];

// --------------------------------------------------------------------------------------
// Blur
// --------------------------------------------------------------------------------------

/**
 * Blurs an array of data in-place by applying three iterations of a moving average transform (box filter)
 * for a fast approximation of a Gaussian kernel of the given radius, a non-negative number.
 * Returns the given data.
 */
export function blur(data: ArrayLike<number>, radius: number): ArrayLike<number>;

/**
 * Blurs a matrix of the given width and height in-place by applying a horizontal blur of radius rx
 * and a vertical blur of radius ry (which defaults to rx).
 * The matrix values data are stored in a flat (one-dimensional) array.
 * If height is not specified, it is inferred from the given width and data.length.
 * Returns the blurred matrix {data, width, height}.
 */
export function blur2(data: Matrix, rx: number, ry?: number): Matrix;

/**
 * Blurs the given ImageData in-place, blurring each of the RGBA layers independently by applying an horizontal blur of radius rx
 * and a vertical blur of radius ry (which defaults to rx).
 * Returns the blurred ImageData.
 */
export function blurImage(imageData: ImageData, rx: number, ry?: number): ImageData;

// --------------------------------------------------------------------------------------
// Iterables
// --------------------------------------------------------------------------------------

/**
 * Returns true if the given test function returns true for every value in the given iterable.
 * This method returns as soon as test returns a non-truthy value or all values are iterated over.
 * Equivalent to array.every.
 */
export function every<T>(
    iterable: Iterable<T>,
    test: (value: T, index: number, iterable: Iterable<T>) => unknown,
): boolean;

/**
 * Returns true if the given test function returns true for any value in the given iterable.
 * This method returns as soon as test returns a truthy value or all values are iterated over.
 * Equivalent to array.some.
 */
export function some<T>(
    iterable: Iterable<T>,
    test: (value: T, index: number, iterable: Iterable<T>) => unknown,
): boolean;

/**
 * Returns a new array containing the values from iterable, in order, for which the given test function returns true.
 * Equivalent to array.filter.
 */
export function filter<T>(
    iterable: Iterable<T>,
    test: (value: T, index: number, iterable: Iterable<T>) => unknown,
): T[];

/**
 * Returns a new array containing the mapped values from iterable, in order, as defined by given mapper function.
 * Equivalent to array.map and Array.from.
 */
export function map<T, U>(iterable: Iterable<T>, mapper: (value: T, index: number, iterable: Iterable<T>) => U): U[];

/**
 * Returns the reduced value defined by given reducer function, which is repeatedly invoked for each value in iterable, being passed the current reduced value and the next value.
 * Equivalent to array.reduce.
 */
export function reduce<T>(
    iterable: Iterable<T>,
    reducer: (previousValue: T, currentValue: T, currentIndex: number, iterable: Iterable<T>) => T,
    initialValue?: T,
): T;
/**
 * Returns the reduced value defined by given reducer function, which is repeatedly invoked for each value in iterable, being passed the current reduced value and the next value.
 * Equivalent to array.reduce.
 */
export function reduce<T, U>(
    iterable: Iterable<T>,
    reducer: (previousValue: U, currentValue: T, currentIndex: number, iterable: Iterable<T>) => U,
    initialValue: U,
): U;

/**
 * Returns an array containing the values in the given iterable in reverse order.
 * Equivalent to array.reverse, except that it does not mutate the given iterable.
 */
export function reverse<T>(iterable: Iterable<T>): T[];

/**
 * Returns an array containing the values in the given iterable in the sorted order defined by the given comparator function.
 * If comparator is not specified, it defaults to d3.ascending.
 * Equivalent to array.sort, except that it does not mutate the given iterable, and the comparator defaults to natural order instead of lexicographic order.
 */
export function sort<T>(iterable: Iterable<T>, comparator?: (a: T, b: T) => number): T[];
/**
 * Returns an array containing the values in the given iterable in the sorted order defined by the given accessor function.
 * This is equivalent to a comparator using natural order.
 * The accessor is only invoked once per element, and thus may be nondeterministic.
 * Multiple accessors may be specified to break ties.
 */
export function sort<T>(iterable: Iterable<T>, ...accessors: Array<(a: T) => unknown>): T[];

// --------------------------------------------------------------------------------------
// Sets
// --------------------------------------------------------------------------------------

/**
 * Returns a new InternSet containing every value in iterable that is not in any of the others iterables.
 */
export function difference<T>(iterable: Iterable<T>, ...others: Array<Iterable<T>>): InternSet<T>;

/**
 * Returns a new InternSet containing every (distinct) value that appears in any of the given iterables.
 * The order of values in the returned set is based on their first occurrence in the given iterables.
 */
export function union<T>(...iterables: Array<Iterable<T>>): InternSet<T>;

/**
 * Returns a new InternSet containing every (distinct) value that appears in all of the given iterables.
 * The order of values in the returned set is based on their first occurrence in the given iterables.
 */
export function intersection<T>(...iterables: Array<Iterable<T>>): InternSet<T>;

/**
 * Returns true if a is a superset of b: if every value in the given iterable b is also in the given iterable a.
 */
export function superset<T>(a: Iterable<T>, b: Iterable<T>): boolean;

/**
 * Returns true if a is a subset of b: if every value in the given iterable a is also in the given iterable b.
 */
export function subset<T>(a: Iterable<T>, b: Iterable<T>): boolean;

/**
 * Returns true if a and b are disjoint: if a and b contain no shared value.
 */
export function disjoint<T>(a: Iterable<T>, b: Iterable<T>): boolean;

// --------------------------------------------------------------------------------------
// Bins
// --------------------------------------------------------------------------------------

export interface Bin<Datum, Value extends number | Date | undefined> extends Array<Datum> {
    x0: Value | undefined;
    x1: Value | undefined;
}

/**
 * Type definition for threshold generator which returns the count of recommended thresholds
 */
export type ThresholdCountGenerator<Value extends number | undefined = number | undefined> = (
    values: ArrayLike<Value>,
    min: number,
    max: number,
) => number;

/**
 * Type definition for threshold generator which returns an array of recommended numbers thresholds
 */
export type ThresholdNumberArrayGenerator<Value extends number | undefined> = (
    values: ArrayLike<Value>,
    min: number,
    max: number,
) => Value[];

/**
 * Type definition for threshold generator which returns an array of recommended dates thresholds
 */
export type ThresholdDateArrayGenerator<Value extends Date | undefined> = (
    values: ArrayLike<Value>,
    min: Date,
    max: Date,
) => Value[];

export interface HistogramCommon<Datum, Value extends number | Date | undefined> {
    (data: ArrayLike<Datum>): Array<Bin<Datum, Value>>;

    value(): (d: Datum, i: number, data: ArrayLike<Datum>) => Value;
    value(valueAccessor: (d: Datum, i: number, data: ArrayLike<Datum>) => Value): this;
}

export interface HistogramGeneratorDate<Datum, Value extends Date | undefined> extends HistogramCommon<Datum, Date> {
    domain(): (values: ArrayLike<Value>) => [Date, Date];
    domain(domain: [Date, Date] | ((values: ArrayLike<Value>) => [Date, Date])): this;

    thresholds(): ThresholdDateArrayGenerator<Value>;
    /**
     * Set the array of values to be used as thresholds in determining the bins.
     *
     * Any threshold values outside the domain are ignored. The first bin.x0 is always equal to the minimum domain value,
     * and the last bin.x1 is always equal to the maximum domain value.
     *
     * @param thresholds Either an array of threshold values used for binning. The elements must
     * be of the same type as the materialized values of the histogram.
     * Or a function which accepts as arguments the array of materialized values, and
     * optionally the domain minimum and maximum. The function calculates and returns the array of values to be used as
     * thresholds in determining the bins.
     */
    thresholds(thresholds: ArrayLike<Value> | ThresholdDateArrayGenerator<Value>): this;
}

export interface HistogramGeneratorNumber<Datum, Value extends number | undefined>
    extends HistogramCommon<Datum, Value>
{
    domain(): (values: Iterable<Value>) => [number, number] | [undefined, undefined];
    domain(domain: [number, number] | ((values: Iterable<Value>) => [number, number] | [undefined, undefined])): this;

    thresholds(): ThresholdCountGenerator<Value> | ThresholdNumberArrayGenerator<Value>;
    /**
     * Divide the domain uniformly into approximately count bins. IMPORTANT: This threshold
     * setting approach only works, when the materialized values are numbers!
     *
     * Any threshold values outside the domain are ignored. The first bin.x0 is always equal to the minimum domain value,
     * and the last bin.x1 is always equal to the maximum domain value.
     *
     * @param count Either the desired number of uniform bins or a function which accepts as arguments the array of
     * materialized values, and optionally the domain minimum and maximum. The function calculates and returns the
     * suggested number of bins.
     */
    thresholds(count: number | ThresholdCountGenerator<Value>): this;
    /**
     * Set the array of values to be used as thresholds in determining the bins.
     *
     * Any threshold values outside the domain are ignored. The first bin.x0 is always equal to the minimum domain value,
     * and the last bin.x1 is always equal to the maximum domain value.
     *
     * @param thresholds Either an array of threshold values used for binning. The elements must
     * be of the same type as the materialized values of the histogram.
     * Or a function which accepts as arguments the array of materialized values, and
     * optionally the domain minimum and maximum. The function calculates and returns the array of values to be used as
     * thresholds in determining the bins.
     */
    // tslint:disable-next-line:unified-signatures
    thresholds(thresholds: ArrayLike<Value> | ThresholdNumberArrayGenerator<Value>): this;
}

/**
 * @deprecated Use bin instead.
 */
export function histogram(): HistogramGeneratorNumber<number, number>;

/**
 * @deprecated Use bin instead.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function histogram<Datum, Value extends number | undefined>(): HistogramGeneratorNumber<Datum, Value>;

/**
 * @deprecated Use bin instead.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function histogram<Datum, Value extends Date | undefined>(): HistogramGeneratorDate<Datum, Value>;

export function bin(): HistogramGeneratorNumber<number, number>;
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function bin<Datum, Value extends number | undefined>(): HistogramGeneratorNumber<Datum, Value>;
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function bin<Datum, Value extends Date | undefined>(): HistogramGeneratorDate<Datum, Value>;

// --------------------------------------------------------------------------------------
// Histogram Thresholds
// --------------------------------------------------------------------------------------

export function thresholdFreedmanDiaconis(values: ArrayLike<number | undefined>, min: number, max: number): number; // of type ThresholdCountGenerator

export function thresholdScott(values: ArrayLike<number | undefined>, min: number, max: number): number; // of type ThresholdCountGenerator

export function thresholdSturges(values: ArrayLike<number | undefined>): number; // of type ThresholdCountGenerator

// --------------------------------------------------------------------------------------
// Interning
// --------------------------------------------------------------------------------------

/**
 * The InternMap class extends the native JavaScript Map class, allowing Dates and other non-primitive keys by bypassing the SameValueZero algorithm when determining key equality.
 */
export class InternMap<K = any, V = any> extends Map<K, V> {
}

/**
 * The InternSet class extends the native JavaScript Set class, allowing Dates and other non-primitive keys by bypassing the SameValueZero algorithm when determining key equality.
 */
export class InternSet<T = any> extends Set<T> {
}
