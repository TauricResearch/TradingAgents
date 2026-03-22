// Last module patch version validated against: 3.1.0

// ---------------------------------------------------------------------------
// Shared Type Definitions and Interfaces
// ---------------------------------------------------------------------------

/**
 * Type allowing for color objects from a specified color space
 */
export type ColorSpaceObject = RGBColor | HSLColor | LabColor | HCLColor | CubehelixColor;

/**
 * A helper interface of methods common to color objects (including colors defined outside the d3-color standard module,
 * e.g. in d3-hsv). This interface
 */
export interface ColorCommonInstance {
    /**
     * Returns true if and only if the color is displayable on standard hardware.
     * For example, this returns false for an RGB color if any channel value is less than zero or greater than 255, or if the opacity is not in the range [0, 1].
     */
    displayable(): boolean;
    /**
     * Returns a string representing this color according to the CSS Object Model specification,
     * such as rgb(247, 234, 186) or rgba(247, 234, 186, 0.2).
     * If this color is not displayable, a suitable displayable color is returned instead.
     * For example, RGB channel values greater than 255 are clamped to 255.
     */
    toString(): string;
    /**
     * Returns a brighter copy of this color. If k is specified, it controls how much brighter the returned color should be.
     * If k is not specified, it defaults to 1. The behavior of this method is dependent on the implementing color space.
     *
     * @param k A color space dependent number to determine, how much brighter the returned color should be.
     */
    brighter(k?: number): this;
    /**
     * Returns a darker copy of this color. If k is specified, it controls how much darker the returned color should be.
     * If k is not specified, it defaults to 1. The behavior of this method is dependent on the implementing color space.
     *
     * @param k A color space dependent number to determine, how much darker the returned color should be.
     */
    darker(k?: number): this;
    /**
     * Returns the RGB equivalent of this color. For RGB colors, that’s "this".
     */
    rgb(): RGBColor;
    /**
     * Returns a hexadecimal string representing this color.
     * If this color is not displayable, a suitable displayable color is returned instead.
     * For example, RGB channel values greater than 255 are clamped to 255.
     */
    hex(): string;
}

/**
 * A Color object which serves as a base class for
 * colorspace-specific sub-class implementations.
 */
export interface Color {
    /**
     * Returns true if and only if the color is displayable on standard hardware.
     * For example, this returns false for an RGB color if any channel value is less than zero or greater than 255, or if the opacity is not in the range [0, 1].
     */
    displayable(): boolean; // Note: While this method is used in prototyping for colors of specific colorspaces, it should not be called directly, as 'this.rgb' would not be implemented on Color
    /**
     * Returns a string representing this color according to the CSS Object Model specification,
     * such as rgb(247, 234, 186) or rgba(247, 234, 186, 0.2).
     * If this color is not displayable, a suitable displayable color is returned instead.
     * For example, RGB channel values greater than 255 are clamped to 255.
     */
    toString(): string; // Note: While this method is used in prototyping for colors of specific colorspaces, it should not be called directly, as 'this.rgb' would not be implemented on Color
    /**
     * Returns a hexadecimal string representing this color in RGB space, such as #f7eaba.
     * If this color is not displayable, a suitable displayable color is returned instead.
     * For example, RGB channel values greater than 255 are clamped to 255.
     */
    formatHex(): string;
    /**
     * Returns a hexadecimal string representing this color in RGBA space, such as #f7eaba90.
     * If this color is not displayable, a suitable displayable color is returned instead.
     * For example, RGB channel values greater than 255 are clamped to 255.
     */
    formatHex8(): string;
    /**
     * Returns a string representing this color according to the CSS Color Module Level 3 specification, such as hsl(257, 50%, 80%) or hsla(257, 50%, 80%, 0.2).
     * If this color is not displayable, a suitable displayable color is returned instead by clamping S and L channel values to the interval [0, 100].
     */
    formatHsl(): string;
    /**
     * Returns a string representing this color according to the CSS Object Model specification, such as rgb(247, 234, 186) or rgba(247, 234, 186, 0.2).
     * If this color is not displayable, a suitable displayable color is returned instead by clamping RGB channel values to the interval [0, 255].
     */
    formatRgb(): string;
    /**
     * @deprecated Use color.formatHex.
     */
    hex(): string;
}

/**
 * A Color factory object, which may also be used with instanceof to test if an object is a color instance.
 */
export interface ColorFactory extends Function {
    /**
     * Parses the specified CSS Color Module Level 3 specifier string, returning an RGB or HSL color.
     * If the specifier was not valid, null is returned.
     *
     * @param cssColorSpecifier A CSS Color Module Level 3 specifier string.
     */
    (cssColorSpecifier: string): RGBColor | HSLColor | null;
    /**
     * Converts the provided color instance and returns an RGB or HSL color.
     *
     * @param color A permissible color space instance.
     */
    (color: ColorSpaceObject | ColorCommonInstance): RGBColor | HSLColor;
    /**
     * Prototype of the factory, which can be used for instanceof testing
     */
    readonly prototype: Color;
}

/**
 * An RGB color object.
 */
export interface RGBColor extends Color {
    /**
     * Value of red channel
     */
    r: number;
    /**
     * Value of green channel
     */
    g: number;
    /**
     * Value of blue channel
     */
    b: number;
    /**
     * Opacity value
     */
    opacity: number;
    /**
     * Returns a brighter copy of this color. If k is specified, it controls how much brighter the returned color should be.
     * If k is not specified, it defaults to 1.
     *
     * @param k A color space dependent number to determine, how much brighter the returned color should be.
     */
    brighter(k?: number): this;
    /**
     * Returns a darker copy of this color. If k is specified, it controls how much darker the returned color should be.
     * If k is not specified, it defaults to 1.
     *
     * @param k A color space dependent number to determine, how much darker the returned color should be.
     */
    darker(k?: number): this;
    /**
     * Returns the RGB equivalent of this color.
     */
    rgb(): this;
    /**
     * Returns a copy of this color.
     *
     * @param values If values is specified, any enumerable own properties of values are assigned to the new returned color.
     */
    copy(
        values?: {
            r?: number | undefined;
            g?: number | undefined;
            b?: number | undefined;
            opacity?: number | undefined;
        },
    ): this;
    /**
     * Returns a new RGB color where the r, g, and b channels are clamped to the range [0, 255] and rounded to the nearest integer value,
     * and the opacity is clamped to the range [0, 1].
     */
    clamp(): this;
}

/**
 * An RGB color factory object, which may also be used with instanceof to test if an object
 * is an RGB color instance.
 */
export interface RGBColorFactory extends Function {
    /**
     * Constructs a new RGB color based on the specified channel values and opacity.
     *
     * @param r Red channel value.
     * @param g Green channel value.
     * @param b Blue channel value.
     * @param opacity Optional opacity value, defaults to 1.
     */
    (r: number, g: number, b: number, opacity?: number): RGBColor;
    /**
     * Parses the specified CSS Color Module Level 3 specifier string, returning an RGB color.
     * If the specifier was not valid, null is returned.
     *
     * @param cssColorSpecifier A CSS Color Module Level 3 specifier string.
     */
    (cssColorSpecifier: string): RGBColor;
    /**
     * Converts the provided color instance and returns an RGB color. The color instance is converted to the RGB color space using color.rgb.
     * Note that unlike color.rgb this method always returns a new instance, even if color is already an RGB color.
     *
     * @param color A permissible color space instance.
     */
    // tslint:disable-next-line:unified-signatures
    (color: ColorSpaceObject | ColorCommonInstance): RGBColor;
    /**
     * Prototype of the factory, which can be used for instanceof testing
     */
    readonly prototype: RGBColor;
}

/**
 * An HSL color object.
 */
export interface HSLColor extends Color {
    /**
     * Hue channel value.
     */
    h: number;
    /**
     * Saturation channel value.
     */
    s: number;
    /**
     * Lightness channel value.
     */
    l: number;
    /**
     * Opacity value.
     */
    opacity: number;
    /**
     * Returns a brighter copy of this color. If k is specified, it controls how much brighter the returned color should be.
     * If k is not specified, it defaults to 1.
     *
     * @param k A color space dependent number to determine, how much brighter the returned color should be.
     */
    brighter(k?: number): this;
    /**
     * Returns a darker copy of this color. If k is specified, it controls how much darker the returned color should be.
     * If k is not specified, it defaults to 1.
     *
     * @param k A color space dependent number to determine, how much darker the returned color should be.
     */
    darker(k?: number): this;
    /**
     * Returns the RGB color equivalent of this color.
     */
    rgb(): RGBColor;
    /**
     * Returns a copy of this color.
     *
     * @param values If values is specified, any enumerable own properties of values are assigned to the new returned color.
     */
    copy(
        values?: {
            h?: number | undefined;
            s?: number | undefined;
            l?: number | undefined;
            opacity?: number | undefined;
        },
    ): this;
    /**
     * Returns a new HSL color where the h channel is clamped to the range [0, 360), and the s, l, and opacity channels are clamped to the range [0, 1].
     */
    clamp(): this;
}

/**
 * An HSL color factory object, which may also be used with instanceof to test if an object
 * is an HSL color instance.
 */
export interface HSLColorFactory extends Function {
    /**
     * Constructs a new HSL color based on the specified channel values and opacity.
     *
     * @param h Hue channel value.
     * @param s Saturation channel value.
     * @param l Lightness channel value.
     * @param opacity Optional opacity value, defaults to 1.
     */
    (h: number, s: number, l: number, opacity?: number): HSLColor;
    /**
     * Parses the specified CSS Color Module Level 3 specifier string, returning an HSL color.
     * If the specifier was not valid, null is returned.
     *
     * @param cssColorSpecifier A CSS Color Module Level 3 specifier string.
     */
    (cssColorSpecifier: string): HSLColor;
    /**
     * Converts the provided color instance and returns an HSL color.
     * The color instance is converted to the RGB color space using color.rgb and then converted to HSL.
     * (Colors already in the HSL color space skip the conversion to RGB.)
     *
     * @param color A permissible color space instance.
     */
    // tslint:disable-next-line:unified-signatures
    (color: ColorSpaceObject | ColorCommonInstance): HSLColor;
    /**
     * Prototype of the factory, which can be used for instanceof testing
     */
    readonly prototype: HSLColor;
}

/**
 * A Lab (CIELAB) color object.
 */
export interface LabColor extends Color {
    /**
     * Lightness typically in the range [0, 100].
     */
    l: number;
    /**
     * Position between red/magenta and green typically in [-160, +160].
     */
    a: number;
    /**
     * Position between yellow and blue typically in [-160, +160].
     */
    b: number;
    /**
     * Opacity value
     */
    opacity: number;
    /**
     * Returns a brighter copy of this color. If k is specified, it controls how much brighter the returned color should be.
     * If k is not specified, it defaults to 1.
     *
     * @param k A color space dependent number to determine, how much brighter the returned color should be.
     */
    brighter(k?: number): this;
    /**
     * Returns a darker copy of this color. If k is specified, it controls how much darker the returned color should be.
     * If k is not specified, it defaults to 1.
     *
     * @param k A color space dependent number to determine, how much darker the returned color should be.
     */
    darker(k?: number): this;
    /**
     * Returns the RGB color equivalent of this color.
     */
    rgb(): RGBColor;
    /**
     * Returns a copy of this color.
     *
     * @param values If values is specified, any enumerable own properties of values are assigned to the new returned color.
     */
    copy(
        values?: {
            l?: number | undefined;
            a?: number | undefined;
            b?: number | undefined;
            opacity?: number | undefined;
        },
    ): this;
}

/**
 * A Lab (CIELAB) color factory object, which may also be used with instanceof to test if an object
 * is a Lab color instance.
 */
export interface LabColorFactory extends Function {
    /**
     * Constructs a new CIELAB color based on the specified channel values and opacity.
     *
     * @param l Lightness typically in the range [0, 100].
     * @param a Position between red/magenta and green typically in [-160, +160].
     * @param b Position between yellow and blue typically in [-160, +160].
     * @param opacity Optional opacity value, defaults to 1.
     */
    (l: number, a: number, b: number, opacity?: number): LabColor;
    /**
     * Parses the specified CSS Color Module Level 3 specifier string, returning a Lab color.
     * If the specifier was not valid, null is returned.
     *
     * @param cssColorSpecifier A CSS Color Module Level 3 specifier string.
     */
    (cssColorSpecifier: string): LabColor;
    /**
     * Converts the provided color instance and returns a Lab color.
     * The color instance is converted to the RGB color space using color.rgb and then converted to CIELAB.
     * (Colors already in the Lab color space skip the conversion to RGB,
     * and colors in the HCL color space are converted directly to CIELAB.)
     *
     * @param color A permissible color space instance.
     */
    // tslint:disable-next-line:unified-signatures
    (color: ColorSpaceObject | ColorCommonInstance): LabColor;
    /**
     * Prototype of the factory, which can be used for instanceof testing
     */
    readonly prototype: LabColor;
}

/**
 * A gray color factory for Lab (CIELAB) colors.
 */
export type GrayColorFactory =
    /**
     * Constructs a new CIELAB color with the specified l value and a = b = 0.
     *
     * @param l Lightness typically in the range [0, 100].
     * @param opacity Optional opacity value, defaults to 1.
     */
    (l: number, opacity?: number) => LabColor;

/**
 * An HCL (CIELCH) color object.
 */
export interface HCLColor extends Color {
    /**
     * Hue channel value typically in [0, 360).
     */
    h: number;
    /**
     * Chroma channel value typically in [0, 230].
     */
    c: number;
    /**
     * Luminance channel value typically in the range [0, 100].
     */
    l: number;
    /**
     * Opacity value
     */
    opacity: number;
    /**
     * Returns a brighter copy of this color. If k is specified, it controls how much brighter the returned color should be.
     * If k is not specified, it defaults to 1.
     *
     * @param k A color space dependent number to determine, how much brighter the returned color should be.
     */
    brighter(k?: number): this;
    /**
     * Returns a darker copy of this color. If k is specified, it controls how much darker the returned color should be.
     * If k is not specified, it defaults to 1.
     *
     * @param k A color space dependent number to determine, how much darker the returned color should be.
     */
    darker(k?: number): this;
    /**
     * Returns the RGB color equivalent of this color.
     */
    rgb(): RGBColor;
    /**
     * Returns a copy of this color.
     *
     * @param values If values is specified, any enumerable own properties of values are assigned to the new returned color.
     */
    copy(
        values?: {
            h?: number | undefined;
            c?: number | undefined;
            l?: number | undefined;
            opacity?: number | undefined;
        },
    ): this;
}

/**
 * An HCL (CIELCH) color factory object, which may also be used with instanceof to test if an object
 * is an HCL color instance.
 */
export interface HCLColorFactory extends Function {
    /**
     * Constructs a new HCL color based on the specified channel values and opacity.
     *
     * @param h Hue channel value typically in [0, 360).
     * @param c Chroma channel value typically in [0, 230].
     * @param l Luminance channel value typically in the range [0, 100].
     * @param opacity Optional opacity value, defaults to 1.
     */
    (h: number, c: number, l: number, opacity?: number): HCLColor;
    /**
     * Parses the specified CSS Color Module Level 3 specifier string, returning an HCL color.
     * If the specifier was not valid, null is returned.
     *
     * @param cssColorSpecifier A CSS Color Module Level 3 specifier string.
     */
    (cssColorSpecifier: string): HCLColor;
    /**
     * Converts the provided color instance and returns an HCL color.
     * The color instance is converted to the RGB color space using color.rgb and then converted to HCL.
     * (Colors already in the HCL color space skip the conversion to RGB,
     * and colors in the Lab color space are converted directly to HCL.)
     *
     * @param color A permissible color space instance.
     */
    // tslint:disable-next-line:unified-signatures
    (color: ColorSpaceObject | ColorCommonInstance): HCLColor;
    /**
     * Prototype of the factory, which can be used for instanceof testing
     */
    readonly prototype: HCLColor;
}

/**
 * An LCH (CIELCH) color factory function to create an HCL color object.
 */
export interface LCHColorFactory {
    /**
     * Constructs a new HCL color based on the specified channel values and opacity.
     *
     * @param l Luminance channel value typically in the range [0, 100].
     * @param c Chroma channel value typically in [0, 230].
     * @param h Hue channel value typically in [0, 360).
     * @param opacity Optional opacity value, defaults to 1.
     */
    (l: number, c: number, h: number, opacity?: number): HCLColor;
    /**
     * Parses the specified CSS Color Module Level 3 specifier string, returning an HCL color.
     * If the specifier was not valid, null is returned.
     *
     * @param cssColorSpecifier A CSS color Module Level 3 specifier string.
     */
    (cssColorSpecifier: string): HCLColor;
    /**
     * Converts the provided color instance and returns an HCL color.
     * The color instance is converted to the RGB color space using color.rgb and then converted to HCL.
     * (Colors already in the HCL color space skip the conversion to RGB,
     * and colors in the Lab color space are converted directly to HCL.)
     *
     * @param color A permissible color space instance.
     */
    // tslint:disable-next-line:unified-signatures
    (color: ColorSpaceObject | ColorCommonInstance): HCLColor;
}

/**
 * Dave Green’s Cubehelix color object.
 */
export interface CubehelixColor extends Color {
    /**
     * Hue channel value.
     */
    h: number;
    /**
     * Saturation channel value.
     */
    s: number;
    /**
     * Lightness channel value.
     */
    l: number;
    /**
     * Opacity value.
     */
    opacity: number;
    /**
     * Returns a brighter copy of this color. If k is specified, it controls how much brighter the returned color should be.
     * If k is not specified, it defaults to 1.
     *
     * @param k A color space dependent number to determine, how much brighter the returned color should be.
     */
    brighter(k?: number): this;
    /**
     * Returns a darker copy of this color. If k is specified, it controls how much darker the returned color should be.
     * If k is not specified, it defaults to 1.
     *
     * @param k A color space dependent number to determine, how much darker the returned color should be.
     */
    darker(k?: number): this;
    /**
     * Returns the RGB color equivalent of this color.
     */
    rgb(): RGBColor;
    /**
     * Returns a copy of this color.
     *
     * @param values If values is specified, any enumerable own properties of values are assigned to the new returned color.
     */
    copy(
        values?: {
            h?: number | undefined;
            s?: number | undefined;
            l?: number | undefined;
            opacity?: number | undefined;
        },
    ): this;
}

/**
 * A color factory object for Dave Green's Cubehelix colors, which may also be used with instanceof to test if an object
 * is a Cubehelix color instance.
 */
export interface CubehelixColorFactory extends Function {
    /**
     * Constructs a new Cubehelix color based on the specified channel values and opacity.
     *
     * @param h Hue channel value.
     * @param s Saturation channel value.
     * @param l Lightness channel value.
     * @param opacity Optional opacity value, defaults to 1.
     */
    (h: number, s: number, l: number, opacity?: number): CubehelixColor;
    /**
     * Parses the specified CSS Color Module Level 3 specifier string, returning an Cubehelix color.
     * If the specifier was not valid, null is returned.
     *
     * @param cssColorSpecifier A CSS Color Module Level 3 specifier string.
     */
    (cssColorSpecifier: string): CubehelixColor;
    /**
     * Converts the provided color instance and returns a Cubehelix color.
     * The color instance is specified, it is converted to the RGB color space using color.rgb and then converted to Cubehelix.
     * (Colors already in the Cubehelix color space skip the conversion to RGB.)
     *
     * @param color A permissible color space instance.
     */
    // tslint:disable-next-line:unified-signatures
    (color: ColorSpaceObject | ColorCommonInstance): CubehelixColor;
    /**
     * Prototype of the factory, which can be used for instanceof testing
     */
    readonly prototype: CubehelixColor;
}

// --------------------------------------------------------------------------
// Color object factories
// --------------------------------------------------------------------------

/**
 * A Color factory object, which may also be used with instanceof to test if an object is a color instance.
 */
export const color: ColorFactory;

/**
 * An RGB color factory object, which may also be used with instanceof to test if an object
 * is an RGB color instance.
 */
export const rgb: RGBColorFactory;

/**
 * An HSL color factory object, which may also be used with instanceof to test if an object
 * is an HSL color instance.
 */
export const hsl: HSLColorFactory;

/**
 * A Lab (CIELAB) color factory object, which may also be used with instanceof to test if an object
 * is a Lab color instance.
 */
export const lab: LabColorFactory;

/**
 * A gray color factory for Lab (CIELAB) colors.
 */
export const gray: GrayColorFactory;

/**
 * An HCL (CIELCH) color factory object, which may also be used with instanceof to test if an object
 * is an HCL color instance.
 */
export const hcl: HCLColorFactory;

/**
 * An LCH (CIELCH) color factory function to create an HCL color object.
 */
export const lch: LCHColorFactory;

/**
 * A color factory object for Dave Green's Cubehelix colors, which may also be used with instanceof to test if an object
 * is a Cubehelix color instance.
 */
export const cubehelix: CubehelixColorFactory;
