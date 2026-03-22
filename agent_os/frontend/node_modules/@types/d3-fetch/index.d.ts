// Last module patch version validated against: 3.0.1

import { DSVParsedArray, DSVRowArray, DSVRowString } from "d3-dsv";

/**
 * Fetches the binary file at the specified input URL and returns it as a Promise of a Blob.
 * If init is specified, it is passed along to the underlying call to fetch.
 *
 * @param url A valid URL string.
 * @param init An optional request initialization object.
 */
export function blob(url: string, init?: RequestInit): Promise<Blob>;

/**
 * Fetches the binary file at the specified input URL and returns it as a Promise of an ArrayBuffer.
 * If init is specified, it is passed along to the underlying call to fetch.
 *
 * @param url A valid URL string.
 * @param init An optional request initialization object.
 */
export function buffer(url: string, init?: RequestInit): Promise<ArrayBuffer>;

/**
 * Fetches the CSV file at the specified input URL and returns
 * a promise of an array of objects representing the parsed rows. The values of the properties of the parsed row
 * objects are represented as strings.
 *
 * If init is specified, it is passed along to the underlying call to fetch.
 *
 * The generic parameter describes the column names as a union of string literal types.
 *
 * @param url A valid URL string.
 * @param init An optional request initialization object.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function csv<Columns extends string>(
    url: string,
    init?: RequestInit,
): Promise<DSVRowArray<Columns>>;
/**
 * Fetches the CSV file at the specified input URL and returns
 * a promise of an array of objects representing the parsed rows.
 *
 * The specified row conversion function is used to map and filter row objects to a more-specific representation;
 * see dsv.csvParse for details.
 *
 * The first generic parameter describes the type of the object representation of a parsed row.
 * The second generic parameter describes the column names as a union of string literal types.
 *
 * @param url A valid URL string.
 * @param row A row conversion function which is invoked for each row, being passed an object representing the current row (d),
 * the index (i) starting at zero for the first non-header row, and the array of column names. If the returned value is null or undefined,
 * the row is skipped and will be omitted from the array returned by dsv.csvParse; otherwise, the returned value defines the corresponding row object.
 * In effect, row is similar to applying a map and filter operator to the returned rows.
 */
export function csv<ParsedRow extends object, Columns extends string = string>(
    url: string,
    row: (rawRow: DSVRowString<Columns>, index: number, columns: Columns[]) => ParsedRow | undefined | null,
): Promise<DSVParsedArray<ParsedRow>>;
/**
 * Fetches the CSV file at the specified input URL and returns
 * a promise of an array of objects representing the parsed rows.
 *
 * The init object is passed along to the underlying call to fetch.
 *
 * The specified row conversion function is used to map and filter row objects to a more-specific representation;
 * see dsv.csvParse for details.
 *
 * The first generic parameter describes the type of the object representation of a parsed row.
 * The second generic parameter describes the column names as a union of string literal types.
 *
 * @param url A valid URL string.
 * @param init An request initialization object.
 * @param row A row conversion function which is invoked for each row, being passed an object representing the current row (d),
 * the index (i) starting at zero for the first non-header row, and the array of column names. If the returned value is null or undefined,
 * the row is skipped and will be omitted from the array returned by dsv.csvParse; otherwise, the returned value defines the corresponding row object.
 * In effect, row is similar to applying a map and filter operator to the returned rows.
 */
export function csv<ParsedRow extends object, Columns extends string = string>(
    url: string,
    init: RequestInit,
    row: (rawRow: DSVRowString<Columns>, index: number, columns: Columns[]) => ParsedRow | undefined | null,
): Promise<DSVParsedArray<ParsedRow>>;

/**
 * Fetches the DSV file with the specified delimiter character at the specified input URL and returns
 * a promise of an array of objects representing the parsed rows. The values of the properties of the parsed row
 * objects are represented as strings.
 *
 * If init is specified, it is passed along to the underlying call to fetch.
 *
 * The generic parameter describes the column names as a union of string literal types.
 *
 * @param delimiter The delimiter character used in the DSV file to be fetched.
 * @param url A valid URL string.
 * @param init An optional request initialization object.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function dsv<Columns extends string>(
    delimiter: string,
    url: string,
    init?: RequestInit,
): Promise<DSVRowArray<Columns>>;
/**
 * Fetches the DSV file with the specified delimiter character at the specified input URL and returns
 * a promise of an array of objects representing the parsed rows.
 *
 * The specified row conversion function is used to map and filter row objects to a more-specific representation;
 * see dsv.parse for details.
 *
 * The first generic parameter describes the type of the object representation of a parsed row.
 * The second generic parameter describes the column names as a union of string literal types.
 *
 * @param delimiter The delimiter character used in the DSV file to be fetched.
 * @param url A valid URL string.
 * @param row A row conversion function which is invoked for each row, being passed an object representing the current row (d),
 * the index (i) starting at zero for the first non-header row, and the array of column names. If the returned value is null or undefined,
 * the row is skipped and will be omitted from the array returned by dsv.parse; otherwise, the returned value defines the corresponding row object.
 * In effect, row is similar to applying a map and filter operator to the returned rows.
 */
export function dsv<ParsedRow extends object, Columns extends string = string>(
    delimiter: string,
    url: string,
    row: (rawRow: DSVRowString<Columns>, index: number, columns: Columns[]) => ParsedRow | undefined | null,
): Promise<DSVParsedArray<ParsedRow>>;
/**
 * Fetches the DSV file with the specified delimiter character at the specified input URL and returns
 * a promise of an array of objects representing the parsed rows.
 *
 * The init object is passed along to the underlying call to fetch.
 *
 * The specified row conversion function is used to map and filter row objects to a more-specific representation;
 * see dsv.parse for details.
 *
 * The first generic parameter describes the type of the object representation of a parsed row.
 * The second generic parameter describes the column names as a union of string literal types.
 *
 * @param delimiter The delimiter character used in the DSV file to be fetched.
 * @param url A valid URL string.
 * @param init An request initialization object.
 * @param row A row conversion function which is invoked for each row, being passed an object representing the current row (d),
 * the index (i) starting at zero for the first non-header row, and the array of column names. If the returned value is null or undefined,
 * the row is skipped and will be omitted from the array returned by dsv.parse; otherwise, the returned value defines the corresponding row object.
 * In effect, row is similar to applying a map and filter operator to the returned rows.
 */
export function dsv<ParsedRow extends object, Columns extends string = string>(
    delimiter: string,
    url: string,
    init: RequestInit,
    row: (rawRow: DSVRowString<Columns>, index: number, columns: Columns[]) => ParsedRow | undefined | null,
): Promise<DSVParsedArray<ParsedRow>>;

/**
 * Fetches the file at the specified input URL as text, parses it as HTML and returns a Promise of an HTML DOM Document.
 *
 * If init is specified, it is passed along to the underlying call to fetch.
 *
 * @param url A valid URL string.
 * @param init An optional request initialization object.
 */
export function html(url: string, init?: RequestInit): Promise<Document>;

/**
 * Fetches the image at the specified input URL and returns a promise of an HTML image element.
 *
 * If init is specified, sets any additional properties on the image before loading.
 *
 * @param url A valid URL string.
 * @param init An optional object of image properties to set.
 */
export function image(url: string, init?: Partial<HTMLImageElement>): Promise<HTMLImageElement>;

/**
 * Fetches the json file at the specified input URL and returns it as a Promise of a parsed JSON object.
 *
 * If init is specified, it is passed along to the underlying call to fetch.
 *
 * If the server returns a status code of [204 No Content](https://developer.mozilla.org/docs/Web/HTTP/Status/204)
 * or [205 Reset Content](https://developer.mozilla.org/docs/Web/HTTP/Status/205), the promise resolves to `undefined`.
 *
 * The generic parameter describes the type of the object parsed from the returned JSON.
 *
 * @param url A valid URL string.
 * @param init An optional request initialization object.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function json<ParsedJSONObject extends any>(
    url: string,
    init?: RequestInit,
): Promise<ParsedJSONObject | undefined>;

/**
 * Fetches the file at the specified input URL as text, parses it as SVG and returns a Promise of an SVG Document.
 *
 * If init is specified, it is passed along to the underlying call to fetch.
 *
 * @param url A valid URL string.
 * @param init An optional request initialization object.
 */
export function svg(url: string, init?: RequestInit): Promise<Document>;

/**
 * Fetches the text file at the specified input URL and returns it as a Promise of a string.
 *
 * If init is specified, it is passed along to the underlying call to fetch.
 *
 * @param url A valid URL string.
 * @param init An optional request initialization object.
 */
export function text(url: string, init?: RequestInit): Promise<string>;

/**
 * Fetches the TSV file at the specified input URL and returns
 * a promise of an array of objects representing the parsed rows.
 *
 * If init is specified, it is passed along to the underlying call to fetch.
 *
 * The generic parameter describes the column names as a union of string literal types.
 *
 * @param url A valid URL string.
 * @param init An optional request initialization object.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function tsv<Columns extends string>(
    url: string,
    init?: RequestInit,
): Promise<DSVRowArray<Columns>>;
/**
 * Fetches the TSV file at the specified input URL and returns
 * a promise of an array of objects representing the parsed rows. The values of the properties of the parsed row
 * objects are represented as strings.
 *
 * The specified row conversion function is used to map and filter row objects to a more-specific representation;
 * see dsv.tsvParse for details.
 *
 * The first generic parameter describes the type of the object representation of a parsed row.
 * The second generic parameter describes the column names as a union of string literal types.
 *
 * @param url A valid URL string.
 * @param row A row conversion function which is invoked for each row, being passed an object representing the current row (d),
 * the index (i) starting at zero for the first non-header row, and the array of column names. If the returned value is null or undefined,
 * the row is skipped and will be omitted from the array returned by dsv.tsvParse; otherwise, the returned value defines the corresponding row object.
 * In effect, row is similar to applying a map and filter operator to the returned rows.
 */
export function tsv<ParsedRow extends object, Columns extends string = string>(
    url: string,
    row: (rawRow: DSVRowString<Columns>, index: number, columns: Columns[]) => ParsedRow | undefined | null,
): Promise<DSVParsedArray<ParsedRow>>;
/**
 * Fetches the TSV file at the specified input URL and returns
 * a promise of an array of objects representing the parsed rows.
 *
 * The init object is passed along to the underlying call to fetch.
 *
 * The specified row conversion function is used to map and filter row objects to a more-specific representation;
 * see dsv.tsvParse for details.
 *
 * The first generic parameter describes the type of the object representation of a parsed row.
 * The second generic parameter describes the column names as a union of string literal types.
 *
 * @param url A valid URL string.
 * @param init An request initialization object.
 * @param row A row conversion function which is invoked for each row, being passed an object representing the current row (d),
 * the index (i) starting at zero for the first non-header row, and the array of column names. If the returned value is null or undefined,
 * the row is skipped and will be omitted from the array returned by dsv.tsvParse; otherwise, the returned value defines the corresponding row object.
 * In effect, row is similar to applying a map and filter operator to the returned rows.
 */
export function tsv<ParsedRow extends object, Columns extends string = string>(
    url: string,
    init: RequestInit,
    row: (rawRow: DSVRowString<Columns>, index: number, columns: Columns[]) => ParsedRow | undefined | null,
): Promise<DSVParsedArray<ParsedRow>>;

/**
 * Fetches the file at the specified input URL as text, parses it as XML and returns a Promise of an XML Document.
 *
 * If init is specified, it is passed along to the underlying call to fetch.
 *
 * @param url A valid URL string.
 * @param init An optional request initialization object.
 */
export function xml(url: string, init?: RequestInit): Promise<XMLDocument>;
