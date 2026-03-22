// Last module patch version validated against: 4.0.0

/**
 * Specification of time locale to use when creating a new TimeLocaleObject
 */
export interface TimeLocaleDefinition {
    /**
     * The date and time (%c) format specifier (e.g., "%a %b %e %X %Y").
     */
    dateTime: string;
    /**
     * The date (%x) format specifier (e.g., "%m/%d/%Y").
     */
    date: string;
    /**
     *  The time (%X) format specifier (e.g., "%H:%M:%S").
     */
    time: string;
    /**
     * The A.M. and P.M. equivalents (e.g., ["AM", "PM"]).
     */
    periods: [string, string];
    /**
     * The full names of the weekdays, starting with Sunday.
     */
    days: [string, string, string, string, string, string, string];
    /**
     * The abbreviated names of the weekdays, starting with Sunday.
     */
    shortDays: [string, string, string, string, string, string, string];
    /**
     * The full names of the months (starting with January).
     */
    months: [string, string, string, string, string, string, string, string, string, string, string, string];
    /**
     * the abbreviated names of the months (starting with January).
     */
    shortMonths: [string, string, string, string, string, string, string, string, string, string, string, string];
}

/**
 * Interface describing a time-locale-based object which exposes time-formatting/parsing
 * methods for a specified locale definition.
 */
export interface TimeLocaleObject {
    /**
     * Returns a new formatter for the given string specifier. The specifier string may contain the following directives:
     * - %a - abbreviated weekday name.*
     * - %A - full weekday name.*
     * - %b - abbreviated month name.*
     * - %B - full month name.*
     * - %c - the locale’s date and time, such as %x, %X.*
     * - %d - zero-padded day of the month as a decimal number [01,31].
     * - %e - space-padded day of the month as a decimal number [ 1,31]; equivalent to %_d.
     * - %f - microseconds as a decimal number [000000, 999999].
     * - %g - ISO 8601 week-based year without century as a decimal number [00,99].
     * - %G - ISO 8601 week-based year with century as a decimal number.
     * - %H - hour (24-hour clock) as a decimal number [00,23].
     * - %I - hour (12-hour clock) as a decimal number [01,12].
     * - %j - day of the year as a decimal number [001,366].
     * - %m - month as a decimal number [01,12].
     * - %M - minute as a decimal number [00,59].
     * - %L - milliseconds as a decimal number [000, 999].
     * - %p - either AM or PM.*
     * - %q - quarter of the year as a decimal number [1,4].
     * - %Q - milliseconds since UNIX epoch.
     * - %s - seconds since UNIX epoch.
     * - %S - second as a decimal number [00,61].
     * - %u - Monday-based (ISO) weekday as a decimal number [1,7].
     * - %U - Sunday-based week of the year as a decimal number [00,53].
     * - %V - ISO 8601 week number of the year as a decimal number [01, 53].
     * - %w - Sunday-based weekday as a decimal number [0,6].
     * - %W - Monday-based week of the year as a decimal number [00,53].
     * - %x - the locale’s date, such as %-m/%-d/%Y.*
     * - %X - the locale’s time, such as %-I:%M:%S %p.*
     * - %y - year without century as a decimal number [00,99].
     * - %Y - year with century as a decimal number.
     * - %Z - time zone offset, such as -0700, -07:00, -07, or Z.
     * - %% - a literal percent sign (%).
     *
     * Directives marked with an asterisk (*) may be affected by the locale definition.
     *
     * For %U, all days in a new year preceding the first Sunday are considered to be in week 0.
     * For %W, all days in a new year preceding the first Monday are considered to be in week 0.
     * Week numbers are computed using interval.count. For example, 2015-52 and 2016-00 represent Monday, December 28, 2015, while 2015-53 and 2016-01 represent Monday, January 4, 2016.
     * This differs from the ISO week date specification (%V), which uses a more complicated definition!
     *
     * For %V,%g and %G, per the strftime man page:
     *
     * In this system, weeks start on a Monday, and are numbered from 01, for the first week, up to 52 or 53, for the last week.
     * Week 1 is the first week where four or more days fall within the new year (or, synonymously, week 01 is: the first week of the year that contains a Thursday;
     * or, the week that has 4 January in it). If the ISO week number belongs to the previous or next year, that year is used instead.
     *
     * The % sign indicating a directive may be immediately followed by a padding modifier:
     *
     * 1) 0 - zero-padding
     * 2) _ - space-padding
     * 3) - disable padding
     *
     * If no padding modifier is specified, the default is 0 for all directives except %e, which defaults to _.
     * (In some implementations of strftime and strptime, a directive may include an optional field width or precision; this feature is not yet implemented.)
     *
     * The returned function formats a specified date, returning the corresponding string.
     *
     * @param specifier A specifier string for the date format.
     */
    format(specifier: string): (date: Date) => string;
    /**
     * Returns a new parser for the given string specifier. The specifier string may contain the same directives as locale.format (TimeLocaleObject.format).
     * The %d and %e directives are considered equivalent for parsing.
     *
     * The returned function parses a specified string, returning the corresponding date or null if the string could not be parsed according to this format’s specifier.
     * Parsing is strict: if the specified string does not exactly match the associated specifier, this method returns null.
     *
     * For example, if the associated specifier is %Y-%m-%dT%H:%M:%SZ, then the string "2011-07-01T19:15:28Z" will be parsed as expected,
     * but "2011-07-01T19:15:28", "2011-07-01 19:15:28" and "2011-07-01" will return null. (Note that the literal Z here is different from the time zone offset directive %Z.)
     * If a more flexible parser is desired, try multiple formats sequentially until one returns non-null.
     *
     * @param specifier A specifier string for the date format.
     */
    parse(specifier: string): (dateString: string) => Date | null;
    /**
     * Equivalent to locale.format (TimeLocaleObject.format), except all directives are interpreted as Coordinated Universal Time (UTC) rather than local time.
     *
     * @param specifier A specifier string for the date format.
     */
    utcFormat(specifier: string): (date: Date) => string;
    /**
     * Equivalent to locale.parse (TimeLocaleObject.parse), except all directives are interpreted as Coordinated Universal Time (UTC) rather than local time.
     *
     * @param specifier A specifier string for the date format.
     */
    utcParse(specifier: string): (dateString: string) => Date | null;
}

/**
 * Create a new time-locale-based object which exposes time-formatting
 * methods for the specified locale definition.
 *
 * @param definition A time locale definition.
 */
export function timeFormatLocale(definition: TimeLocaleDefinition): TimeLocaleObject;

/**
 * Create a new time-locale-based object which exposes time-formatting
 * methods for the specified locale definition. The new time locale definition
 * will be set as the new default time locale.
 *
 * @param definition A time locale definition.
 */
export function timeFormatDefaultLocale(definition: TimeLocaleDefinition): TimeLocaleObject;

/**
 * Returns a new formatter for the given string specifier. The returned function formats a specified date, returning the corresponding string.
 *
 * An alias for locale.format (TimeLocaleObject.format) on the default locale.
 *
 * @param specifier A specifier string for the date format.
 */
export function timeFormat(specifier: string): (date: Date) => string;

/**
 * Returns a new parser for the given string specifier.
 *
 * An alias for locale.parse (TimeLocaleObject.parse) on the default locale.
 *
 * @param specifier A specifier string for the date format.
 */
export function timeParse(specifier: string): (dateString: string) => Date | null;

/**
 * Equivalent to timeFormat, except all directives are interpreted as Coordinated Universal Time (UTC) rather than local time.
 *
 * An alias for locale.utcFormat (TimeLocaleObject.utcFormat) on the default locale.
 *
 * @param specifier A specifier string for the date format.
 */
export function utcFormat(specifier: string): (date: Date) => string;

/**
 * Equivalent to timeParse, except all directives are interpreted as Coordinated Universal Time (UTC) rather than local time.
 *
 * An alias for locale.utcParse (TimeLocaleObject.utcParse) on the default locale.
 *
 * @param specifier A specifier string for the date format.
 */
export function utcParse(specifier: string): (dateString: string) => Date | null;

/**
 * The full ISO 8601 UTC time formatter. Where available, this method will use Date.toISOString to format.
 *
 * @param date A date to format.
 */
export function isoFormat(date: Date): string;

/**
 * The full ISO 8601 UTC time parser. Where available, this method will use the Date constructor to parse strings.
 * If you depend on strict validation of the input format according to ISO 8601, you should construct a UTC parser function using utcParse.
 *
 * @param dateString A string encoded date to parse.
 */
export function isoParse(dateString: string): Date | null;
