// Last module patch version validated against: 3.0.1

// ------------------------------------------------------------------------------------------
// Shared Types and Interfaces
// ------------------------------------------------------------------------------------------

/**
 * An object representing a DSV parsed row with values represented as strings.
 */
export type DSVRowString<Columns extends string = string> = {
    [key in Columns]: string;
};

/**
 * An object in raw format before parsing, that is with only string values.
 */
export type DSVRaw<T extends object> = {
    [key in keyof T]: string;
};

/**
 * An object representing a DSV parsed row with values represented as an arbitrary datatype, depending
 * on the performed parsed row mapping.
 *
 * @deprecated Use `object` instead.
 */
export interface DSVRowAny {
    [key: string]: any;
}

/**
 * An array object representing all deserialized rows. The array is enhanced with a property listing
 * the names of the parsed columns.
 */
export interface DSVRowArray<Columns extends string = string> extends Array<DSVRowString<Columns>> {
    /**
     * List of column names.
     */
    columns: Columns[];
}

/**
 * An array object representing all parsed rows. The array is enhanced with a property listing
 * the names of the parsed columns.
 */
export interface DSVParsedArray<T> extends Array<T> {
    /**
     * List of column names.
     */
    columns: Array<keyof T>;
}

// ------------------------------------------------------------------------------------------
// CSV Parsers and Formatters
// ------------------------------------------------------------------------------------------

// csvParse(...) ============================================================================

/**
 * Parses the specified string, which must be in the comma-separated values format, returning an array of objects representing the parsed rows.
 *
 * Unlike csvParseRows, this method requires that the first line of the CSV content contains a comma-separated list of column names;
 * these column names become the attributes on the returned objects.
 *
 * The returned array also exposes a columns property containing the column names in input order (in contrast to Object.keys, whose iteration order is arbitrary).
 *
 * Equivalent to `dsvFormat(",").parse`.
 * Note: requires unsafe-eval content security policy.
 *
 * @param csvString A string, which must be in the comma-separated values format.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function csvParse<Columns extends string>(csvString: string): DSVRowArray<Columns>;
/**
 * Parses the specified string, which must be in the comma-separated values format, returning an array of objects representing the parsed rows.
 *
 * Unlike csvParseRows, this method requires that the first line of the CSV content contains a comma-separated list of column names;
 * these column names become the attributes on the returned objects.
 *
 * The returned array also exposes a columns property containing the column names in input order (in contrast to Object.keys, whose iteration order is arbitrary).
 *
 * Equivalent to `dsvFormat(",").parse`.
 * Note: requires unsafe-eval content security policy.
 *
 * @param csvString A string, which must be in the comma-separated values format.
 * @param row A row conversion function which is invoked for each row, being passed an object representing the current row (d),
 * the index (i) starting at zero for the first non-header row, and the array of column names. If the returned value is null or undefined,
 * the row is skipped and will be omitted from the array returned by dsv.parse; otherwise, the returned value defines the corresponding row object.
 * In effect, row is similar to applying a map and filter operator to the returned rows.
 */
export function csvParse<ParsedRow extends object, Columns extends string>(
    csvString: string,
    row: (rawRow: DSVRowString<Columns>, index: number, columns: Columns[]) => ParsedRow | undefined | null,
): DSVParsedArray<ParsedRow>;

// csvParseRows(...) ========================================================================

/**
 * Parses the specified string, which must be in the comma-separated values format, returning an array of arrays representing the parsed rows.
 *
 * Unlike csvParse, this method treats the header line as a standard row, and should be used whenever CSV content does not contain a header.
 * Each row is represented as an array rather than an object. Rows may have variable length.
 *
 * If a row conversion function is not specified, field values are strings. For safety, there is no automatic conversion to numbers, dates, or other types.
 * In some cases, JavaScript may coerce strings to numbers for you automatically (for example, using the + operator), but better is to specify a row conversion function.
 *
 * Equivalent to `dsvFormat(",").parseRows`.
 *
 * @param csvString A string, which must be in the comma-separated values format.
 */
export function csvParseRows(csvString: string): string[][];
/**
 * Parses the specified string, which must be in the comma-separated values format, returning an array of arrays representing the parsed rows.
 *
 * Unlike csvParse, this method treats the header line as a standard row, and should be used whenever CSV content does not contain a header.
 * Each row is represented as an array rather than an object. Rows may have variable length.
 *
 * Equivalent to `dsvFormat(",").parseRows`.
 *
 * @param csvString A string, which must be in the comma-separated values format.
 * @param row A row conversion function which is invoked for each row, being passed an array representing the current row (d), the index (i)
 * starting at zero for the first row, and the array of column names. If the returned value is null or undefined,
 * the row is skipped and will be omitted from the array returned by dsv.parse; otherwise, the returned value defines the corresponding row object.
 * In effect, row is similar to applying a map and filter operator to the returned rows.
 */
export function csvParseRows<ParsedRow extends object>(
    csvString: string,
    row: (rawRow: string[], index: number) => ParsedRow | undefined | null,
): ParsedRow[];

// csvFormat(...) ============================================================================

/**
 * Formats the specified array of object rows as comma-separated values, returning a string.
 * This operation is the inverse of csvParse. Each row will be separated by a newline (\n),
 * and each column within each row will be separated by the comma-delimiter.
 * Values that contain either the comma-delimiter, a double-quote (") or a newline will be escaped using double-quotes.
 *
 * If columns is not specified, the list of column names that forms the header row is determined by the union of all properties on all objects in rows;
 * the order of columns is nondeterministic.
 *
 * Equivalent to `dsvFormat(",").format`.
 *
 * @param rows Array of object rows.
 * @param columns An array of strings representing the column names.
 */
export function csvFormat<T extends object>(rows: readonly T[], columns?: ReadonlyArray<keyof T>): string;

// csvFormatBody(...) ============================================================================

/**
 * Equivalent to dsvFormat(",").formatBody.
 *
 * @param rows Array of object rows.
 * @param columns An array of strings representing the column names.
 */
export function csvFormatBody<T extends object>(rows: readonly T[], columns?: ReadonlyArray<keyof T>): string;

// csvFormatRows(...) ========================================================================

/**
 * Formats the specified array of array of string rows as comma-separated values, returning a string.
 * This operation is the reverse of csvParseRows. Each row will be separated by a newline (\n),
 * and each column within each row will be separated by the comma-delimiter.
 * Values that contain either the comma-delimiter, a double-quote (") or a newline will be escaped using double-quotes.
 *
 * To convert an array of objects to an array of arrays while explicitly specifying the columns, use array.map.
 * If you like, you can also array.concat this result with an array of column names to generate the first row.
 *
 * Equivalent to `dsvFormat(",").formatRows`.
 *
 * @param rows An array of array of string rows.
 */
export function csvFormatRows(rows: readonly string[][]): string;

// csvFormatRow(...) ========================================================================

/**
 * Equivalent to dsvFormat(",").formatRow.
 *
 * @param row An array of strings representing a row.
 */
export function csvFormatRow(row: readonly string[]): string;

// csvFormatValue(...) ========================================================================

/**
 * Equivalent to dsvFormat(",").formatValue.
 *
 * @param value A value.
 */
export function csvFormatValue(value: string): string;

// ------------------------------------------------------------------------------------------
// TSV Parsers and Formatters
// ------------------------------------------------------------------------------------------

// tsvParse(...) ============================================================================

/**
 * Parses the specified string, which must be in the tab-separated values format, returning an array of objects representing the parsed rows.
 *
 * Unlike tsvParseRows, this method requires that the first line of the TSV content contains a tab-separated list of column names;
 * these column names become the attributes on the returned objects.
 *
 * The returned array also exposes a columns property containing the column names in input order (in contrast to Object.keys, whose iteration order is arbitrary).
 *
 * Equivalent to `dsvFormat("\t").parse`.
 * Note: requires unsafe-eval content security policy.
 *
 * @param tsvString A string, which must be in the tab-separated values format.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function tsvParse<Columns extends string>(tsvString: string): DSVRowArray<Columns>;
/**
 * Parses the specified string, which must be in the tab-separated values format, returning an array of objects representing the parsed rows.
 *
 * Unlike tsvParseRows, this method requires that the first line of the TSV content contains a tab-separated list of column names;
 * these column names become the attributes on the returned objects.
 *
 * The returned array also exposes a columns property containing the column names in input order (in contrast to Object.keys, whose iteration order is arbitrary).
 *
 * Equivalent to `dsvFormat("\t").parse`.
 * Note: requires unsafe-eval content security policy.
 *
 * @param tsvString A string, which must be in the tab-separated values format.
 * @param row A row conversion function which is invoked for each row, being passed an object representing the current row (d),
 * the index (i) starting at zero for the first non-header row, and the array of column names. If the returned value is null or undefined,
 * the row is skipped and will be omitted from the array returned by dsv.parse; otherwise, the returned value defines the corresponding row object.
 * In effect, row is similar to applying a map and filter operator to the returned rows.
 */
export function tsvParse<ParsedRow extends object, Columns extends string>(
    tsvString: string,
    row: (rawRow: DSVRowString<Columns>, index: number, columns: Columns[]) => ParsedRow | undefined | null,
): DSVParsedArray<ParsedRow>;

// tsvParseRows(...) ========================================================================

/**
 * Parses the specified string, which must be in the tab-separated values format, returning an array of arrays representing the parsed rows.
 *
 * Unlike tsvParse, this method treats the header line as a standard row, and should be used whenever TSV content does not contain a header.
 * Each row is represented as an array rather than an object. Rows may have variable length.
 *
 * If a row conversion function is not specified, field values are strings. For safety, there is no automatic conversion to numbers, dates, or other types.
 * In some cases, JavaScript may coerce strings to numbers for you automatically (for example, using the + operator), but better is to specify a row conversion function.
 *
 * Equivalent to `dsvFormat("\t").parseRows`.
 *
 * @param tsvString A string, which must be in the tab-separated values format.
 */
export function tsvParseRows(tsvString: string): string[][];
/**
 * Parses the specified string, which must be in the tab-separated values format, returning an array of arrays representing the parsed rows.
 *
 * Unlike tsvParse, this method treats the header line as a standard row, and should be used whenever TSV content does not contain a header.
 * Each row is represented as an array rather than an object. Rows may have variable length.
 *
 * Equivalent to `dsvFormat("\t").parseRows`.
 *
 * @param tsvString A string, which must be in the tab-separated values format.
 * @param row A row conversion function which is invoked for each row, being passed an array representing the current row (d), the index (i)
 * starting at zero for the first row, and the array of column names. If the returned value is null or undefined,
 * the row is skipped and will be omitted from the array returned by dsv.parse; otherwise, the returned value defines the corresponding row object.
 * In effect, row is similar to applying a map and filter operator to the returned rows.
 */
export function tsvParseRows<ParsedRow extends object>(
    tsvString: string,
    row: (rawRow: string[], index: number) => ParsedRow | undefined | null,
): ParsedRow[];

// tsvFormat(...) ============================================================================

/**
 * Formats the specified array of object rows as tab-separated values, returning a string.
 * This operation is the inverse of tsvParse. Each row will be separated by a newline (\n),
 * and each column within each row will be separated by the tab-delimiter.
 * Values that contain either the tab-delimiter, a double-quote (") or a newline will be escaped using double-quotes.
 *
 * If columns is not specified, the list of column names that forms the header row is determined by the union of all properties on all objects in rows;
 * the order of columns is nondeterministic.
 *
 * Equivalent to `dsvFormat("\t").format`.
 *
 * @param rows Array of object rows.
 * @param columns An array of strings representing the column names.
 */
export function tsvFormat<T extends object>(rows: readonly T[], columns?: ReadonlyArray<keyof T>): string;

// tsvFormatBody(...) ============================================================================

/**
 * Equivalent to dsvFormat("\t").formatBody.
 *
 * @param rows Array of object rows.
 * @param columns An array of strings representing the column names.
 */
export function tsvFormatBody<T extends object>(rows: readonly T[], columns?: ReadonlyArray<keyof T>): string;

// tsvFormatRows(...) ========================================================================

/**
 * Formats the specified array of array of string rows as tab-separated values, returning a string.
 * This operation is the reverse of tsvParseRows. Each row will be separated by a newline (\n),
 * and each column within each row will be separated by the tab-delimiter.
 * Values that contain either the tab-delimiter, a double-quote (") or a newline will be escaped using double-quotes.
 *
 * To convert an array of objects to an array of arrays while explicitly specifying the columns, use array.map.
 * If you like, you can also array.concat this result with an array of column names to generate the first row.
 *
 * Equivalent to `dsvFormat("\t").formatRows`.
 *
 * @param rows An array of array of string rows.
 */
export function tsvFormatRows(rows: readonly string[][]): string;

// tsvFormatRow(...) ========================================================================

/**
 * Equivalent to dsvFormat("\t").formatRow.
 *
 * @param row An array of strings representing a row.
 */
export function tsvFormatRow(row: readonly string[]): string;

// tsvFormatValue(...) ========================================================================

/**
 * Equivalent to dsvFormat("\t").formatValue.
 *
 * @param value A value.
 */
export function tsvFormatValue(value: string): string;

// ------------------------------------------------------------------------------------------
// DSV Generalized Parsers and Formatters
// ------------------------------------------------------------------------------------------

/**
 * A DSV parser and formatter
 */
export interface DSV {
    /**
     * Parses the specified string, which must be in the delimiter-separated values format with the appropriate delimiter, returning an array of objects representing the parsed rows.
     *
     * Unlike dsv.parseRows, this method requires that the first line of the DSV content contains a delimiter-separated list of column names;
     * these column names become the attributes on the returned objects.
     *
     * The returned array also exposes a columns property containing the column names in input order (in contrast to Object.keys, whose iteration order is arbitrary).
     *
     * If the column names are not unique, only the last value is returned for each name; to access all values, use dsv.parseRows instead.
     *
     * Note: requires unsafe-eval content security policy.
     *
     * @param dsvString A string, which must be in the delimiter-separated values format with the appropriate delimiter.
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    parse<Columns extends string>(dsvString: string): DSVRowArray<Columns>;
    /**
     * Parses the specified string, which must be in the delimiter-separated values format with the appropriate delimiter, returning an array of objects representing the parsed rows.
     *
     * Unlike dsv.parseRows, this method requires that the first line of the DSV content contains a delimiter-separated list of column names;
     * these column names become the attributes on the returned objects.
     *
     * The returned array also exposes a columns property containing the column names in input order (in contrast to Object.keys, whose iteration order is arbitrary).
     *
     * If the column names are not unique, only the last value is returned for each name; to access all values, use dsv.parseRows instead.
     *
     * Note: requires unsafe-eval content security policy.
     *
     * @param dsvString A string, which must be in the delimiter-separated values format with the appropriate delimiter.
     * @param row A row conversion function which is invoked for each row, being passed an object representing the current row (d),
     * the index (i) starting at zero for the first non-header row, and the array of column names. If the returned value is null or undefined,
     * the row is skipped and will be omitted from the array returned by dsv.parse; otherwise, the returned value defines the corresponding row object.
     * In effect, row is similar to applying a map and filter operator to the returned rows.
     */
    parse<ParsedRow extends object, Columns extends string>(
        dsvString: string,
        row: (rawRow: DSVRowString<Columns>, index: number, columns: Columns[]) => ParsedRow | undefined | null,
    ): DSVParsedArray<ParsedRow>;

    /**
     * Parses the specified string, which must be in the delimiter-separated values format with the appropriate delimiter, returning an array of arrays representing the parsed rows.
     *
     * Unlike dsv.parse, this method treats the header line as a standard row, and should be used whenever DSV content does not contain a header.
     * Each row is represented as an array rather than an object. Rows may have variable length.
     *
     * If a row conversion function is not specified, field values are strings. For safety, there is no automatic conversion to numbers, dates, or other types.
     * In some cases, JavaScript may coerce strings to numbers for you automatically (for example, using the + operator), but better is to specify a row conversion function.
     *
     * @param dsvString A string, which must be in the delimiter-separated values format with the appropriate delimiter.
     */
    parseRows(dsvString: string): string[][];
    /**
     * Parses the specified string, which must be in the delimiter-separated values format with the appropriate delimiter, returning an array of arrays representing the parsed rows.
     *
     * Unlike dsv.parse, this method treats the header line as a standard row, and should be used whenever DSV content does not contain a header.
     * Each row is represented as an array rather than an object. Rows may have variable length.
     *
     * @param dsvString A string, which must be in the delimiter-separated values format with the appropriate delimiter.
     * @param row A row conversion function which is invoked for each row, being passed an array representing the current row (d), the index (i)
     * starting at zero for the first row, and the array of column names. If the returned value is null or undefined,
     * the row is skipped and will be omitted from the array returned by dsv.parse; otherwise, the returned value defines the corresponding row object.
     * In effect, row is similar to applying a map and filter operator to the returned rows.
     */
    parseRows<ParsedRow extends object>(
        dsvString: string,
        row: (rawRow: string[], index: number) => ParsedRow | undefined | null,
    ): ParsedRow[];

    /**
     * Formats the specified array of object rows as delimiter-separated values, returning a string.
     * This operation is the inverse of dsv.parse. Each row will be separated by a newline (\n),
     * and each column within each row will be separated by the delimiter (such as a comma, ,).
     * Values that contain either the delimiter, a double-quote (") or a newline will be escaped using double-quotes.
     *
     * If columns is not specified, the list of column names that forms the header row is determined by the union of all properties on all objects in rows;
     * the order of columns is nondeterministic.
     *
     * @param rows Array of object rows.
     * @param columns An array of strings representing the column names.
     */
    format<T extends object>(rows: readonly T[], columns?: ReadonlyArray<keyof T>): string;

    /**
     * Equivalent to dsv.format, but omits the header row.
     * This is useful, for example, when appending rows to an existing file.
     *
     * @param rows Array of object rows.
     * @param columns An array of strings representing the column names.
     */
    formatBody<T extends object>(rows: readonly T[], columns?: ReadonlyArray<keyof T>): string;

    /**
     * Formats the specified array of array of string rows as delimiter-separated values, returning a string.
     * This operation is the reverse of dsv.parseRows. Each row will be separated by a newline (\n),
     * and each column within each row will be separated by the delimiter (such as a comma, ,).
     * Values that contain either the delimiter, a double-quote (") or a newline will be escaped using double-quotes.
     *
     * To convert an array of objects to an array of arrays while explicitly specifying the columns, use array.map.
     * If you like, you can also array.concat this result with an array of column names to generate the first row.
     *
     * @param rows An array of array of string rows.
     */
    formatRows(rows: readonly string[][]): string;

    /**
     * Formats a single array row of strings as delimiter-separated values, returning a string.
     * Each column within the row will be separated by the delimiter (such as a comma, ,).
     * Values that contain either the delimiter, a double-quote (") or a newline will be escaped using double-quotes.
     *
     * @param row An array of strings representing a row.
     */
    formatRow(row: readonly string[]): string;

    /**
     * Format a single value or string as a delimiter-separated value, returning a string.
     * A value that contains either the delimiter, a double-quote (") or a newline will be escaped using double-quotes.
     *
     * @param value A value.
     */
    formatValue(value: string): string;
}

/**
 * Constructs a new DSV parser and formatter for the specified delimiter.
 *
 * @param delimiter A delimiter character. The delimiter must be a single character (i.e., a single 16-bit code unit);
 * so, ASCII delimiters are fine, but emoji delimiters are not.
 */
export function dsvFormat(delimiter: string): DSV;

/**
 * Infers the types of values on the object and coerces them accordingly, returning the mutated object.
 * This function is intended to be used as a row accessor function in conjunction with dsv.parse and dsv.parseRows.
 *
 * @param object An object (or array) representing a parsed row
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function autoType<ParsedRow extends object | undefined | null, Columns extends string>(
    object: DSVRowString<Columns> | readonly string[],
): ParsedRow;
