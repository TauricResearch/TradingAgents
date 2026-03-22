// Last module patch version validated against: 3.0.1

import * as GeoJSON from "geojson";

// ----------------------------------------------------------------------
// Shared Interfaces and Types
// ----------------------------------------------------------------------

/**
 * A basic geometry for a sphere, which is supported by d3-geo
 * beyond the GeoJSON geometries.
 */
export interface GeoSphere {
    /**
     * Sphere geometry type
     */
    type: "Sphere";
}

/**
 * Type Alias for GeoJSON Geometry Object and GeoSphere additional
 * geometry supported by d3-geo
 */
export type GeoGeometryObjects = GeoJSON.GeometryObject | GeoSphere;

/**
 * A GeoJSON-style GeometryCollection which supports GeoJSON geometry objects
 * and additionally GeoSphere.
 *
 * The generic refers to the type(s) of d3-geo geometry objects contained in the collection.
 */
export interface ExtendedGeometryCollection<GeometryType extends GeoGeometryObjects = GeoGeometryObjects> {
    type: string;
    bbox?: number[] | undefined;
    crs?: {
        type: string;
        properties: any;
    } | undefined;
    geometries: GeometryType[];
}

/**
 * A GeoJSON-style Feature which support features built on GeoJSON GeometryObjects
 * or GeoSphere.
 *
 * The first generic refers to the type(s) of d3-geo geometry objects underlying the ExtendedFeature.
 * Unless explicitly ruled out, the geometry value is nullable.
 *
 * The second generic refers to the data type of the properties of the ExtendedFeature. Unless explicitly ruled out,
 * the properties value is nullable.
 */
export interface ExtendedFeature<
    GeometryType extends GeoGeometryObjects | null = GeoGeometryObjects | null,
    Properties extends GeoJSON.GeoJsonProperties = GeoJSON.GeoJsonProperties,
> extends GeoJSON.GeoJsonObject {
    geometry: GeometryType;
    properties: Properties;
    id?: string | number | undefined;
}

/**
 * A GeoJSON-style FeatureCollection which supports GeoJSON features
 * and features built on GeoSphere
 *
 * The generic refers to the type of ExtendedFeature contained in the ExtendedFeatureCollection.
 */
export interface ExtendedFeatureCollection<FeatureType extends ExtendedFeature = ExtendedFeature>
    extends GeoJSON.GeoJsonObject
{
    features: FeatureType[];
}

/**
 * Type Alias for permissible objects which can be used with d3-geo
 * methods
 */
export type GeoPermissibleObjects =
    | GeoGeometryObjects
    | ExtendedGeometryCollection
    | ExtendedFeature
    | ExtendedFeatureCollection;

// ----------------------------------------------------------------------
// Spherical Math
// ----------------------------------------------------------------------

/**
 * Returns the spherical area of the specified GeoJSON object in steradians.
 * This is the spherical equivalent of path.area.
 */
export function geoArea(
    object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
): number;

/**
 * Returns the spherical bounding box for the specified GeoJSON object.
 * The bounding box is represented by a two-dimensional array: [[left, bottom], [right, top]],
 * where left is the minimum longitude, bottom is the minimum latitude, right is maximum longitude, and top is the maximum latitude.
 * All coordinates are given in degrees.
 * (Note that in projected planar coordinates, the minimum latitude is typically the maximum y-value, and the maximum latitude is typically the minimum y-value.)
 * This is the spherical equivalent of path.bounds.
 */
export function geoBounds(
    object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
): [[number, number], [number, number]];

/**
 * Returns the spherical centroid of the specified GeoJSON object.
 * This is the spherical equivalent of path.centroid.
 */
export function geoCentroid(
    object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
): [number, number];

/**
 * Returns true if and only if the specified GeoJSON object contains the specified point, or false if the object does not contain the point.
 * The point must be specified as a two-element array [longitude, latitude] in degrees.
 * For Point and MultiPoint geometries, an exact test is used; for a Sphere, true is always returned; for other geometries, an epsilon threshold is applied.
 */
export function geoContains(
    object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
    point: [number, number],
): boolean;

/**
 * Returns the great-arc distance in radians between the two points a and b.
 * Each point must be specified as a two-element array [longitude, latitude] in degrees.
 *
 * @param a Point specified as a two-element array [longitude, latitude] in degrees.
 * @param b Point specified as a two-element array [longitude, latitude] in degrees.
 */
export function geoDistance(a: [number, number], b: [number, number]): number;

/**
 * Returns the great-arc length of the specified GeoJSON object in radians.
 * For polygons, returns the perimeter of the exterior ring plus that of any interior rings.
 * This is the spherical equivalent of path.measure.
 */
export function geoLength(
    object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
): number;

/**
 * Returns an interpolator function given two points a and b.
 * Each point must be specified as a two-element array [longitude, latitude] in degrees.
 *
 * @param a Point specified as a two-element array [longitude, latitude] in degrees.
 * @param b Point specified as a two-element array [longitude, latitude] in degrees.
 */
export function geoInterpolate(a: [number, number], b: [number, number]): (t: number) => [number, number];

/**
 * A Geo Rotation
 */
export interface GeoRotation {
    /**
     * Returns a new array [longitude, latitude] in degrees representing the rotated point of the given point.
     *
     * @param point The point must be specified as a two-element array [longitude, latitude] in degrees.
     */
    (point: [number, number]): [number, number];

    /**
     * Returns a new array [longitude, latitude] in degrees representing the point of the given rotated point; the inverse of rotation.
     *
     * @param point The rotated point must be specified as a two-element array [longitude, latitude] in degrees.
     */
    invert(point: [number, number]): [number, number];
}

/**
 * Returns a rotation function for the given angles.
 *
 * @param angles  A two- or three-element array of numbers [lambda, phi, gamma] specifying the rotation angles in degrees about each spherical axis.
 * (These correspond to yaw, pitch and roll.) If the rotation angle gamma is omitted, it defaults to 0.
 */
export function geoRotation(angles: [number, number] | [number, number, number]): GeoRotation;

// ----------------------------------------------------------------------
// Spherical Shapes
// ----------------------------------------------------------------------

// geoCircle ============================================================

/**
 * A new circle generator
 *
 * The first generic corresponds to the "this"-context within which the geo circle generator will be invoked.
 *
 * The second generic corresponds to the type of the Datum which will be passed into the geo circle generator.
 */
export interface GeoCircleGenerator<This = any, Datum = any> {
    /**
     * Returns a new GeoJSON geometry object of type “Polygon” approximating a circle on the surface of a sphere,
     * with the current center, radius and precision. Any arguments are passed to the accessors.
     */
    (this: This, d?: Datum, ...args: any[]): GeoJSON.Polygon;

    /**
     * Returns the current center accessor, which defaults to a function returning [0, 0].
     */
    center(): (this: This, d: Datum, ...args: any[]) => [number, number];
    /**
     * Sets the circle center to the specified point [longitude, latitude] in degrees, and returns this circle generator.
     * The center may also be specified as a function; this function will be invoked whenever a circle is generated, being passed any arguments passed to the circle generator.
     */
    center(center: [number, number] | ((this: This, d: Datum, ...args: any[]) => [number, number])): this;

    /**
     * Returns the current radius accessor, which defaults to a function returning 90.
     */
    radius(): (this: This, d: Datum, ...args: any[]) => number;
    /**
     * Sets the circle radius to the specified angle in degrees, and returns this circle generator.
     * The radius may also be specified as a function; this function will be invoked whenever a circle is generated, being passed any arguments passed to the circle generator.
     */
    radius(radius: number | ((this: This, d: Datum, ...args: any[]) => number)): this;

    /**
     * Returns the current precision accessor, which defaults to a function returning 6.
     */
    precision(): (this: This, d: Datum, ...args: any[]) => number;
    /**
     * Sets the circle precision to the specified angle in degrees, and returns this circle generator.
     * The precision may also be specified as a function; this function will be invoked whenever a circle is generated, being passed any arguments passed to the circle generator.
     */
    precision(precision: number | ((this: This, d: Datum, ...args: any[]) => number)): this;
}

/**
 * Returns a new geo circle generator
 */
export function geoCircle(): GeoCircleGenerator;
/**
 * Returns a new geo circle generator
 *
 * The generic corresponds to the data type of the first argument passed into the geo circle generator and its accessor functions.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function geoCircle<Datum>(): GeoCircleGenerator<any, Datum>;
/**
 * Returns a new geo circle generator
 *
 * The first generic corresponds to the "this" context within which the geo circle generator and its accessors will be invoked.
 *
 * The second generic corresponds to the data type of the first argument passed into the geo circle generator and its accessor functions.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function geoCircle<This, Datum>(): GeoCircleGenerator<This, Datum>;

// geoGraticule ============================================================

/**
 * A Feature generator for graticules: a uniform grid of meridians and parallels for showing projection distortion.
 * The default graticule has meridians and parallels every 10° between ±80° latitude; for the polar regions, there are meridians every 90°.
 */
export interface GeoGraticuleGenerator {
    /**
     * Returns a GeoJSON MultiLineString geometry object representing all meridians and parallels for this graticule.
     */
    (): GeoJSON.MultiLineString;

    /**
     * Returns an array of GeoJSON LineString geometry objects, one for each meridian or parallel for this graticule.
     */
    lines(): GeoJSON.LineString[];

    /**
     * Returns a GeoJSON Polygon geometry object representing the outline of this graticule, i.e. along the meridians and parallels defining its extent.
     */
    outline(): GeoJSON.Polygon;

    /**
     * Returns the current minor extent, which defaults to ⟨⟨-180°, -80° - ε⟩, ⟨180°, 80° + ε⟩⟩.
     */
    extent(): [[number, number], [number, number]];
    /**
     * Sets the major and minor extents of this graticule.
     *
     * @param extent Extent to use for major and minor extent of graticule.
     */
    extent(extent: [[number, number], [number, number]]): this;

    /**
     * Returns the current major extent, which defaults to ⟨⟨-180°, -90° + ε⟩, ⟨180°, 90° - ε⟩⟩.
     */
    extentMajor(): [[number, number], [number, number]];
    /**
     * Sets the major extent of this graticule.
     *
     * @param extent Major extent of graticule.
     */
    extentMajor(extent: [[number, number], [number, number]]): this;

    /**
     * Returns the current minor extent, which defaults to  ⟨⟨-180°, -80° - ε⟩, ⟨180°, 80° + ε⟩⟩.
     */
    extentMinor(): [[number, number], [number, number]];
    /**
     * Sets the minor extent of this graticule.
     *
     * @param extent Minor extent of graticule.
     */
    extentMinor(extent: [[number, number], [number, number]]): this;

    /**
     * Returns the current minor step, which defaults to ⟨10°, 10°⟩.
     */
    step(): [number, number];
    /**
     * Sets the major and minor step for this graticule
     *
     * @param step Major and minor step to use for this graticule.
     */
    step(step: [number, number]): this;

    /**
     * Returns the current major step, which defaults to ⟨90°, 360°⟩.
     */
    stepMajor(): [number, number];
    /**
     * Sets the major step for this graticule.
     *
     * @param step Major step.
     */
    stepMajor(step: [number, number]): this;

    /**
     * Returns the current major step, which defaults to ⟨10°, 10°⟩.
     */
    stepMinor(): [number, number];
    /**
     * Sets the minor step for this graticule.
     *
     * @param step Minor step.
     */
    stepMinor(step: [number, number]): this;

    /**
     * Returns the current precision, which defaults to 2.5°.
     */
    precision(): number;
    /**
     * Sets the precision for this graticule, in degrees.
     *
     * @param angle Precision in degrees.
     */
    precision(angle: number): this;
}

/**
 * Constructs a feature generator for creating graticules: a uniform grid of meridians and parallels for showing projection distortion.
 * The default graticule has meridians and parallels every 10° between ±80° latitude; for the polar regions, there are meridians every 90°.
 */
export function geoGraticule(): GeoGraticuleGenerator;

/**
 * A convenience method for directly generating the default 10° global graticule as a GeoJSON MultiLineString geometry object.
 */
export function geoGraticule10(): GeoJSON.MultiLineString;

// ----------------------------------------------------------------------
// Projections
// ----------------------------------------------------------------------

/**
 * A D3 geo stream. D3 transforms geometry using a sequence of function calls, rather than materializing intermediate representations, to minimize overhead.
 * Streams must implement several methods to receive input geometry. Streams are inherently stateful; the meaning of a point depends on whether the point is inside of a line,
 * and likewise a line is distinguished from a ring by a polygon. Despite the name “stream”, these method calls are currently synchronous.
 */
export interface GeoStream {
    /**
     * Indicates the end of a line or ring. Within a polygon, indicates the end of a ring.
     * Unlike GeoJSON, the redundant closing coordinate of a ring is not indicated via point, and instead is implied via lineEnd within a polygon.
     */
    lineEnd(): void;

    /**
     * Indicates the start of a line or ring. Within a polygon, indicates the start of a ring. The first ring of a polygon is the exterior ring, and is typically clockwise.
     * Any subsequent rings indicate holes in the polygon, and are typically counterclockwise.
     */
    lineStart(): void;

    /**
     * Indicates a point with the specified coordinates x and y (and optionally z). The coordinate system is unspecified and implementation-dependent;
     * for example, projection streams require spherical coordinates in degrees as input. Outside the context of a polygon or line,
     * a point indicates a point geometry object (Point or MultiPoint). Within a line or polygon ring, the point indicates a control point.
     *
     * @param x x-coordinate of point.
     * @param y y-coordinate of point.
     * @param z Optional z-coordinate of point.
     */
    point(x: number, y: number, z?: number): void;

    /**
     * Indicates the end of a polygon.
     */
    polygonEnd(): void;

    /**
     * Indicates the start of a polygon. The first line of a polygon indicates the exterior ring, and any subsequent lines indicate interior holes.
     */
    polygonStart(): void;

    /**
     * Indicates the sphere (the globe; the unit sphere centered at ⟨0,0,0⟩).
     */
    sphere?(): void;
}

// geoStream(...) =======================================================

/**
 * Streams the specified GeoJSON object to the specified projection stream.
 * While both features and geometry objects are supported as input, the stream interface only describes the geometry, and thus additional feature properties are not visible to streams.
 */
export function geoStream(
    object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
    stream: GeoStream,
): void;

// ----------------------------------------------------------------------
// Projections
// ----------------------------------------------------------------------

/**
 * Raw projections are point transformation functions that are used to implement custom projections; they typically passed to d3.geoProjection or d3.geoProjectionMutator.
 * They are exposed here to facilitate the derivation of related projections.
 * Raw projections take spherical coordinates [lambda, phi] in radians (not degrees!) and return a point [x, y], typically in the unit square centered around the origin.
 */
export interface GeoRawProjection {
    /**
     * Projects the specified point [lambda, phi] in radians, returning a new point [x, y] in unitless coordinates.
     * @param lambda Spherical lambda coordinate in radians.
     * @param phi Spherical phi coordinate in radians.
     */
    (lambda: number, phi: number): [number, number];

    /**
     * Inverts the projected point [x, y] in unitless coordinates, returning an unprojected point in spherical coordinates [lambda, phi] in radians.
     * @param x x-coordinate (unitless).
     * @param y y-coordinate (unitless).
     */
    invert?(x: number, y: number): [number, number];
}

/**
 * An object implementing a stream method
 */
export interface GeoStreamWrapper {
    /**
     * Returns a projection stream for the specified output stream. Any input geometry is projected before being streamed to the output stream.
     * A typical projection involves several geometry transformations: the input geometry is first converted to radians, rotated on three axes,
     * clipped to the small circle or cut along the antimeridian, and lastly projected to the plane with adaptive resampling, scale and translation.
     *
     * @param stream An input stream
     */
    stream(stream: GeoStream): GeoStream;
}

/**
 * A Geographic Projection to transform spherical polygonal geometry to planar polygonal geometry.
 * D3 provides implementations of several classes of standard projections:
 *
 * - Azimuthal
 * - Composite
 * - Conic
 * - Cylindrical
 *
 * For many more projections, see d3-geo-projection. You can implement custom projections using d3.geoProjection or d3.geoProjectionMutator.
 */
export interface GeoProjection extends GeoStreamWrapper {
    /**
     * Returns a new array [x, y] (typically in pixels) representing the projected point of the given point.
     * The point must be specified as a two-element array [longitude, latitude] in degrees.
     * May return null if the specified point has no defined projected position, such as when the point is outside the clipping bounds of the projection.
     *
     * @param point A point specified as a two-dimensional array [longitude, latitude] in degrees.
     */
    (point: [number, number]): [number, number] | null;

    /**
     * Returns a new array [longitude, latitude] in degrees representing the unprojected point of the given projected point.
     * May return null if the specified point has no defined projected position, such as when the point is outside the clipping bounds of the projection.
     *
     * @param point The projected point, specified as a two-element array [x, y] (typically in pixels).
     */
    invert?(point: [number, number]): [number, number] | null;

    /**
     * Returns the current spherical clipping function.
     * Pre-clipping occurs in geographic coordinates. Cutting along the antimeridian line,
     * or clipping along a small circle are the most common strategies.
     */
    preclip(): (stream: GeoStream) => GeoStream;
    /**
     * Sets the projection’s spherical clipping to the specified function and returns the projection.
     * Pre-clipping occurs in geographic coordinates. Cutting along the antimeridian line, or clipping along a small circle are the most common strategies.
     *
     * @param preclip A spherical clipping function. Clipping functions are implemented as transformations of a projection stream.
     * Pre-clipping operates on spherical coordinates, in radians.
     */
    preclip(preclip: (stream: GeoStream) => GeoStream): this;

    /**
     * Returns the current cartesian clipping function.
     * Post-clipping occurs on the plane, when a projection is bounded to a certain extent such as a rectangle.
     */
    postclip(): (stream: GeoStream) => GeoStream;
    /**
     * Sets the projection’s cartesian clipping to the specified function and returns the projection.
     *
     * @param postclip A cartesian clipping function. Clipping functions are implemented as transformations of a projection stream.
     * Post-clipping operates on planar coordinates, in pixels.
     */
    postclip(postclip: (stream: GeoStream) => GeoStream): this;

    /**
     * Returns the current clip angle which defaults to null.
     *
     * null switches to antimeridian cutting rather than small-circle clipping.
     */
    clipAngle(): number | null;
    /**
     * Sets the projection’s clipping circle radius to the specified angle in degrees and returns the projection.
     * If angle is null, switches to antimeridian cutting rather than small-circle clipping.
     */
    clipAngle(angle: null | number): this;

    /**
     * Returns the current viewport clip extent which defaults to null.
     */
    clipExtent(): [[number, number], [number, number]] | null;
    /**
     * Sets the projection’s viewport clip extent to the specified bounds in pixels and returns the projection.
     * The extent bounds are specified as an array [[x₀, y₀], [x₁, y₁]], where x₀ is the left-side of the viewport, y₀ is the top, x₁ is the right and y₁ is the bottom.
     * If extent is null, no viewport clipping is performed.
     */
    clipExtent(extent: null | [[number, number], [number, number]]): this;

    /**
     * Returns the current scale factor; the default scale is projection-specific.
     *
     * The scale factor corresponds linearly to the distance between projected points; however, absolute scale factors are not equivalent across projections.
     */
    scale(): number;
    /**
     * Sets the projection’s scale factor to the specified value and returns the projection.
     * The scale factor corresponds linearly to the distance between projected points; however, absolute scale factors are not equivalent across projections.
     *
     * @param scale Scale factor to be used for the projection; the default scale is projection-specific.
     */
    scale(scale: number): this;

    /**
     * Returns the current translation offset which defaults to [480, 250] and places ⟨0°,0°⟩ at the center of a 960×500 area.
     * The translation offset determines the pixel coordinates of the projection’s center.
     */
    translate(): [number, number];
    /**
     * Sets the projection’s translation offset to the specified two-element array [tx, ty] and returns the projection.
     * The translation offset determines the pixel coordinates of the projection’s center. The default translation offset places ⟨0°,0°⟩ at the center of a 960×500 area.
     *
     * @param point A two-element array [tx, ty] specifying the translation offset. The default translation offset of defaults to [480, 250] places ⟨0°,0°⟩ at the center of a 960×500 area.
     */
    translate(point: [number, number]): this;

    /**
     * Returns the current center of the projection, which defaults to ⟨0°,0°⟩.
     */
    center(): [number, number];
    /**
     * Sets the projection’s center to the specified center,
     * a two-element array of longitude and latitude in degrees and returns the projection.
     * The default is ⟨0°,0°⟩.
     *
     * @param point A point specified as a two-dimensional array [longitude, latitude] in degrees.
     */
    center(point: [number, number]): this;

    /**
     * Returns the projection’s current angle, which defaults to 0°.
     */
    angle(): number;
    /**
     * Sets the projection’s post-projection planar rotation angle to the specified angle in degrees and returns the projection.
     * @param angle The new rotation angle of the projection.
     */
    angle(angle: number): this;

    /**
     * Returns true if x-reflection is enabled, which defaults to false.
     */
    reflectX(): boolean;
    /**
     * Sets whether or not the x-dimension is reflected (negated) in the output.
     * @param reflect Whether or not the x-dimension is reflected (negated) in the output.
     */
    reflectX(reflect: boolean): this;

    /**
     * Returns true if y-reflection is enabled, which defaults to false.
     */
    reflectY(): boolean;
    /**
     * Sets whether or not the y-dimension is reflected (negated) in the output.
     * @param reflect Whether or not the y-dimension is reflected (negated) in the output.
     */
    reflectY(reflect: boolean): this;

    /**
     * Returns the current rotation [lambda, phi, gamma] specifying the rotation angles in degrees about each spherical axis.
     * (These correspond to yaw, pitch and roll.) which defaults [0, 0, 0].
     */
    rotate(): [number, number, number];

    /**
     * Sets the projection’s three-axis rotation to the specified angles, which must be a two- or three-element array of numbers.
     *
     * @param angles  A two- or three-element array of numbers [lambda, phi, gamma] specifying the rotation angles in degrees about each spherical axis.
     * (These correspond to yaw, pitch and roll.) If the rotation angle gamma is omitted, it defaults to 0.
     */
    rotate(angles: [number, number] | [number, number, number]): this;

    /**
     * Returns the projection’s current resampling precision which defaults to square root of 0.5.
     * This value corresponds to the Douglas–Peucker distance.
     */
    precision(): number;
    /**
     * Sets the threshold for the projection’s adaptive resampling to the specified value in pixels and returns the projection.
     * This value corresponds to the Douglas–Peucker distance.
     *
     * @param precision A numeric value in pixels to use as the threshold for the projection’s adaptive resampling.
     */
    precision(precision: number): this;

    /**
     * Sets the projection’s scale and translate to fit the specified GeoJSON object in the center of the given extent.
     * The extent is specified as an array [[x₀, y₀], [x₁, y₁]], where x₀ is the left side of the bounding box, y₀ is the top, x₁ is the right and y₁ is the bottom.
     * Returns the projection.
     */
    fitExtent(
        extent: [[number, number], [number, number]],
        object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
    ): this;

    /**
     * A convenience method for projection.fitExtent where the top-left corner of the extent is [0, 0].
     */
    fitSize(
        size: [number, number],
        object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
    ): this;

    /**
     * A convenience method for projection.fitSize where the height is automatically chosen from the aspect ratio of object and the given constraint on width.
     */
    fitWidth(
        width: number,
        object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
    ): this;

    /**
     * A convenience method for projection.fitSize where the width is automatically chosen from the aspect ratio of object and the given constraint on height.
     */
    fitHeight(
        height: number,
        object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
    ): this;
}

/**
 * A Conic Projection
 */
export interface GeoConicProjection extends GeoProjection {
    /**
     * Return the standard parallels for the conic projection in degrees.
     */
    parallels(): [number, number];
    /**
     * Set the standard parallels for the conic projection in degrees and return the projection.
     *
     * @param value A two-dimensional array representing the standard parallels in degrees.
     */
    parallels(value: [number, number]): this;
}

// geoPath ==============================================================

/**
 * A minimal rendering context for a GeoPath generator. The minimum implemented
 * methods are a subset of the CanvasRenderingContext2D API.
 *
 * For reference to the CanvasRenderingContext2D see https://developer.mozilla.org/en/docs/Web/API/CanvasRenderingContext2D
 */
export interface GeoContext {
    /**
     * Adds an arc to the path with center point (x, y) and radius r starting at startAngle and ending at endAngle.
     * The arc is drawn in clockwise direction by default.
     *
     * @param x x-coordinate of arc center point.
     * @param y y-coordinate of arc center point.
     * @param radius Radius of arc.
     * @param startAngle The starting angle of the arc, measured clockwise from the positive x axis and expressed in radians.
     * @param endAngle The end angle of the arc, measured clockwise from the positive x axis and expressed in radians.
     * @param anticlockwise Optional boolean flag, if true the arc is drawn counter-clockwise between the two angles.
     */
    arc(x: number, y: number, radius: number, startAngle: number, endAngle: number, anticlockwise?: boolean): void;

    /**
     * Start a new path by emptying the list of sub-paths.
     */
    beginPath(): void;

    /**
     * Causes the point of the pen to move back to the start of the current sub-path.
     * It tries to draw a straight line from the current point to the start.
     * If the shape has already been closed or has only one point, this function does nothing.
     */
    closePath(): void;

    /**
     * Connects the last point in the sub-path to the x, y coordinates with a straight line (but does not actually draw it).
     *
     * @param x The x-coordinate for the end of the line.
     * @param y The y-coordinate for the end of the line.
     */
    lineTo(x: number, y: number): void;

    /**
     * Move the starting point of a new sub-path to the (x, y) coordinates.
     *
     * @param x The x-coordinate for the new starting point.
     * @param y The y-coordinate for the new starting point.
     */
    moveTo(x: number, y: number): void;
}

/**
 * A Geo Path generator
 *
 * The first generic corresponds to the "this"-context within which the geo path generator will be invoked.
 * This could be e.g. the DOMElement bound to "this" when using selection.attr("d", ...) with the path generator.
 *
 * The second generic corresponds to the type of the DatumObject which will be passed into the geo path generator for rendering.
 */
export interface GeoPath<This = any, DatumObject extends GeoPermissibleObjects = GeoPermissibleObjects> {
    /**
     * Renders the given object, which may be any GeoJSON feature or geometry object:
     *
     * + Point - a single position.
     * + MultiPoint - an array of positions.
     * + LineString - an array of positions forming a continuous line.
     * + MultiLineString - an array of arrays of positions forming several lines.
     * + Polygon - an array of arrays of positions forming a polygon (possibly with holes).
     * + MultiPolygon - a multidimensional array of positions forming multiple polygons.
     * + GeometryCollection - an array of geometry objects.
     * + Feature - a feature containing one of the above geometry objects.
     * + FeatureCollection - an array of feature objects.
     *
     * The type Sphere is also supported, which is useful for rendering the outline of the globe; a sphere has no coordinates.
     *
     * Any additional arguments are passed along to the pointRadius accessor.
     *
     * IMPORTANT: If the rendering context of the geoPath generator is null,
     * then the geoPath is returned as an SVG path data string.
     *
     * Separate path elements are typically slower than a single path element. However, distinct path elements are useful for styling and interaction (e.g., click or mouseover).
     * Canvas rendering (see path.context) is typically faster than SVG, but requires more effort to implement styling and interaction.
     *
     * The first generic type of the GeoPath generator used, must correspond to the "this" context bound to the function upon invocation.
     *
     * @param object An object to be rendered.
     */
    (this: This, object: DatumObject, ...args: any[]): string | null;
    /**
     * Renders the given object, which may be any GeoJSON feature or geometry object:
     *
     * + Point - a single position.
     * + MultiPoint - an array of positions.
     * + LineString - an array of positions forming a continuous line.
     * + MultiLineString - an array of arrays of positions forming several lines.
     * + Polygon - an array of arrays of positions forming a polygon (possibly with holes).
     * + MultiPolygon - a multidimensional array of positions forming multiple polygons.
     * + GeometryCollection - an array of geometry objects.
     * + Feature - a feature containing one of the above geometry objects.
     * + FeatureCollection - an array of feature objects.
     *
     * The type Sphere is also supported, which is useful for rendering the outline of the globe; a sphere has no coordinates.
     *
     * Any additional arguments are passed along to the pointRadius accessor.
     *
     * IMPORTANT: If the geoPath generator has been configured with a rendering context,
     * then the geoPath is rendered to this context as a sequence of path method calls and this function returns void.
     *
     * Separate path elements are typically slower than a single path element. However, distinct path elements are useful for styling and interaction (e.g., click or mouseover).
     * Canvas rendering (see path.context) is typically faster than SVG, but requires more effort to implement styling and interaction.
     *
     * The first generic type of the GeoPath generator used, must correspond to the "this" context bound to the function upon invocation.
     *
     * @param object An object to be rendered.
     */
    (this: This, object: DatumObject, ...args: any[]): void;

    /**
     * Returns the projected planar area (typically in square pixels) for the specified GeoJSON object.
     * Point, MultiPoint, LineString and MultiLineString geometries have zero area. For Polygon and MultiPolygon geometries,
     * this method first computes the area of the exterior ring, and then subtracts the area of any interior holes.
     * This method observes any clipping performed by the projection; see projection.clipAngle and projection.clipExtent. This is the planar equivalent of d3.geoArea.
     *
     * @param object An object for which the area is to be calculated.
     */
    area(object: DatumObject): number;

    /**
     * Returns the projected planar bounding box (typically in pixels) for the specified GeoJSON object.
     * The bounding box is represented by a two-dimensional array: [[x₀, y₀], [x₁, y₁]], where x₀ is the minimum x-coordinate, y₀ is the minimum y-coordinate,
     * x₁ is maximum x-coordinate, and y₁ is the maximum y-coordinate.
     *
     * This is handy for, say, zooming in to a particular feature. (Note that in projected planar coordinates,
     * the minimum latitude is typically the maximum y-value, and the maximum latitude is typically the minimum y-value.)
     * This method observes any clipping performed by the projection; see projection.clipAngle and projection.clipExtent. This is the planar equivalent of d3.geoBounds.
     *
     * @param object An object for which the bounds are to be calculated.
     */
    bounds(object: DatumObject): [[number, number], [number, number]];

    /**
     * Returns the projected planar centroid (typically in pixels) for the specified GeoJSON object.
     * This is handy for, say, labeling state or county boundaries, or displaying a symbol map.
     * For example, a noncontiguous cartogram might scale each state around its centroid.
     * This method observes any clipping performed by the projection; see projection.clipAngle and projection.clipExtent. This is the planar equivalent of d3.geoCentroid.
     *
     * @param object An object for which the centroid is to be calculated.
     */
    centroid(object: DatumObject): [number, number];

    /**
     * Returns the projected planar length (typically in pixels) for the specified GeoJSON object.
     * Point and MultiPoint geometries have zero length. For Polygon and MultiPolygon geometries, this method computes the summed length of all rings.
     *
     * This method observes any clipping performed by the projection; see projection.clipAngle and projection.clipExtent. This is the planar equivalent of d3.geoLength.
     *
     * @param object An object for which the measure is to be calculated.
     */
    measure(object: DatumObject): number;

    /**
     * Returns the current render context which defaults to null.
     *
     * Use the generic to cast the return type of the rendering context, if it is known for a specific application.
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    context<C extends GeoContext | null>(): C;

    /**
     * sets the current render context and returns the path generator.
     * If the context is null, then the path generator will return an SVG path string;
     * if the context is non-null, the path generator will instead call methods on the specified context to render geometry.
     */
    context(context: null | GeoContext): this;

    /**
     * Get the current projection. The generic parameter can be used to cast the result to the
     * correct, known type of the projection, e.g. GeoProjection or GeoConicProjection. Otherwise,
     * the return type defaults to the minimum type requirement for a projection which
     * can be passed into a GeoPath.
     *
     * Use the generic to cast the return type of the projection, if it is known for a specific application.
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    projection<P extends GeoConicProjection | GeoProjection | GeoStreamWrapper | null>(): P;

    /**
     * Sets the current projection to the specified projection.
     * The null projection represents the identity transformation: the input geometry is not projected and is instead rendered directly in raw coordinates.
     * This can be useful for fast rendering of pre-projected geometry, or for fast rendering of the equirectangular projection.
     */
    projection(projection: null | GeoProjection | GeoStreamWrapper): this;

    /**
     * Returns the current radius or radius accessor used to determine the radius for the display of Point and MultiPoint geometries.
     * The default is a constant radius of 4.5.
     */
    pointRadius(): ((this: This, object: DatumObject, ...args: any[]) => number) | number;

    /**
     * Sets the radius used to display Point and MultiPoint geometries to the specified number.
     * While the radius is commonly specified as a number constant, it may also be specified as a function which is computed per feature, being passed the any arguments passed to the path generator.
     * For example, if your GeoJSON data has additional properties, you might access those properties inside the radius function to vary the point size;
     * alternatively, you could d3.symbol and a projection for greater flexibility.
     */
    pointRadius(value: number | ((this: This, object: DatumObject, ...args: any[]) => number)): this;

    /**
     * Returns the current number of digits, which defaults to 3.
     */
    digits(): number;
    /**
     * Sets the number of fractional digits for coordinates generated in SVG path strings.
     * @param digits New amount of digits
     */
    digits(digits: number): this;
}

/**
 * Creates a new geographic path generator.
 *
 * The default projection is the null projection. The null projection represents the identity transformation, i.e.
 * the input geometry is not projected and is instead rendered directly in raw coordinates.
 * This can be useful for fast rendering of pre-projected geometry, or for fast rendering of the equirectangular projection.
 *
 * The default context is null, which implies that the path generator will return an SVG path string.
 *
 * @param projection An (optional) current projection to be used. Typically this is one of D3’s built-in geographic projections;
 * however, any object that exposes a projection.stream function can be used, enabling the use of custom projections.
 * See D3’s transforms for more examples of arbitrary geometric transformations. Setting the projection to "null" uses the identity projection. The default  value is "null", the identity projection.
 * @param context An (optional) rendering context to be used. If a context is provided, it must at least implement the interface described by GeoContext, a subset of the CanvasRenderingContext2D API.
 * Setting the context to "null" means that the path generator will return an SVG path string representing the to be rendered object. The default is "null".
 */
export function geoPath(projection?: GeoProjection | GeoStreamWrapper | null, context?: GeoContext | null): GeoPath;
/**
 * Creates a new geographic path generator with the default settings.
 *
 * The default projection is the null projection. The null projection represents the identity transformation:
 * the input geometry is not projected and is instead rendered directly in raw coordinates.
 * This can be useful for fast rendering of pre-projected geometry, or for fast rendering of the equirectangular projection.
 *
 * The default context is null, which implies that the path generator will return an SVG path string.
 *
 * The generic corresponds to the type of the DatumObject which will be passed into the geo path generator for rendering
 *
 * @param projection An (optional) current projection to be used. Typically this is one of D3’s built-in geographic projections;
 * however, any object that exposes a projection.stream function can be used, enabling the use of custom projections.
 * See D3’s transforms for more examples of arbitrary geometric transformations. Setting the projection to "null" uses the identity projection. The default  value is "null", the identity projection.
 * @param context An (optional) rendering context to be used. If a context is provided, it must at least implement the interface described by GeoContext, a subset of the CanvasRenderingContext2D API.
 * Setting the context to "null" means that the path generator will return an SVG path string representing the to be rendered object. The default is "null".
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function geoPath<DatumObject extends GeoPermissibleObjects>(
    projection?: GeoProjection | GeoStreamWrapper | null,
    context?: GeoContext | null,
): GeoPath<any, DatumObject>;
/**
 * Creates a new geographic path generator with the default settings.
 *
 * The default projection is the null projection. The null projection represents the identity transformation:
 * the input geometry is not projected and is instead rendered directly in raw coordinates.
 * This can be useful for fast rendering of pre-projected geometry, or for fast rendering of the equirectangular projection.
 *
 * The default context is null, which implies that the path generator will return an SVG path string.
 *
 * The first generic corresponds to the "this"-context within which the geo path generator will be invoked.
 * This could be e.g. the DOMElement bound to "this" when using selection.attr("d", ...) with the path generator.
 *
 * The second generic corresponds to the type of the DatumObject which will be passed into the geo path generator for rendering.
 *
 * @param projection An (optional) current projection to be used. Typically this is one of D3’s built-in geographic projections;
 * however, any object that exposes a projection.stream function can be used, enabling the use of custom projections.
 * See D3’s transforms for more examples of arbitrary geometric transformations. Setting the projection to "null" uses the identity projection. The default  value is "null", the identity projection.
 * @param context An (optional) rendering context to be used. If a context is provided, it must at least implement the interface described by GeoContext, a subset of the CanvasRenderingContext2D API.
 * Setting the context to "null" means that the path generator will return an SVG path string representing the to be rendered object. The default is "null".
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function geoPath<This, DatumObject extends GeoPermissibleObjects>(
    projection?: GeoProjection | GeoStreamWrapper | null,
    context?: GeoContext | null,
): GeoPath<This, DatumObject>;

// geoProjection ==========================================================

/**
 * Constructs a new projection from the specified raw projection, project.
 * The project function takes the longitude and latitude of a given point in radians,
 * often referred to as lambda (λ) and phi (φ), and returns a two-element array [x, y] representing its unit projection.
 * The project function does not need to scale or translate the point, as these are applied automatically by projection.scale, projection.translate, and projection.center.
 * Likewise, the project function does not need to perform any spherical rotation, as projection.rotate is applied prior to projection.
 *
 * If the project function exposes an invert method, the returned projection will also expose projection.invert.
 */
export function geoProjection(project: GeoRawProjection): GeoProjection;

// geoProjectionMutator ====================================================

/**
 * Constructs a new projection from the specified raw projection factory and returns a mutate function to call whenever the raw projection changes.
 * The factory must return a raw projection. The returned mutate function returns the wrapped projection.
 *
 * When creating a mutable projection, the mutate function is typically not exposed.
 */
export function geoProjectionMutator(factory: (...args: any[]) => GeoRawProjection): () => GeoProjection;

// Pre-Defined Projections and Raw Projections =============================

// Azimuthal Projections ---------------------------------------------------

/**
 * The azimuthal equal-area projection.
 */
export function geoAzimuthalEqualArea(): GeoProjection;

/**
 * The raw azimuthal equal-area projection.
 */
export function geoAzimuthalEqualAreaRaw(): GeoRawProjection;

/**
 * The azimuthal equidistant projection.
 */
export function geoAzimuthalEquidistant(): GeoProjection;
/**
 * The raw azimuthal equidistant projection.
 */
export function geoAzimuthalEquidistantRaw(): GeoRawProjection;

/**
 * The gnomonic projection.
 */
export function geoGnomonic(): GeoProjection;

/**
 * The raw gnomonic projection.
 */
export function geoGnomonicRaw(): GeoRawProjection;

/**
 * The orthographic projection.
 */
export function geoOrthographic(): GeoProjection;

/**
 * The raw orthographic projection.
 */
export function geoOrthographicRaw(): GeoRawProjection;

/**
 * The stereographic projection.
 */
export function geoStereographic(): GeoProjection;

/**
 * The raw stereographic projection.
 */
export function geoStereographicRaw(): GeoRawProjection;

/**
 * The Equal Eartch projection, by Bojan Šavrič et al., 2018.
 */
export function geoEqualEarth(): GeoProjection;

/**
 * The raw Equal Earth projection, by Bojan Šavrič et al., 2018.
 */
export function geoEqualEarthRaw(): GeoRawProjection;

// Composite Projections ---------------------------------------------------

/**
 * A U.S.-centric composite projection of three d3.geoConicEqualArea projections: d3.geoAlbers is used for the lower forty-eight states,
 * and separate conic equal-area projections are used for Alaska and Hawaii. Note that the scale for Alaska is diminished: it is projected at 0.35× its true relative area.
 *
 * Composite consist of several projections that are composed into a single display. The constituent projections have fixed clip, center and rotation,
 * and thus composite projections do not support projection.center, projection.rotate, projection.clipAngle, or projection.clipExtent.
 */
export function geoAlbersUsa(): GeoProjection;

// Conic Projections -------------------------------------------------------

/**
 * The Albers’ equal area-conic projection. This is a U.S.-centric configuration of d3.geoConicEqualArea.
 */
export function geoAlbers(): GeoConicProjection;

/**
 * The conic conformal projection. The parallels default to [30°, 30°] resulting in flat top.
 */
export function geoConicConformal(): GeoConicProjection;

/**
 * The raw conic conformal projection.
 */
export function geoConicConformalRaw(phi0: number, phi1: number): GeoRawProjection;

/**
 * The Albers’ equal-area conic projection.
 */
export function geoConicEqualArea(): GeoConicProjection;

/**
 * The raw Albers’ equal-area conic projection.
 */
export function geoConicEqualAreaRaw(phi0: number, phi1: number): GeoRawProjection;

/**
 * The conic equidistant projection.
 */
export function geoConicEquidistant(): GeoConicProjection;

/**
 * The raw conic equidistant projection.
 */
export function geoConicEquidistantRaw(phi0: number, phi1: number): GeoRawProjection;

// Cylindrical Projections ------------------------------------------------

/**
 * The equirectangular (plate carrée) projection.
 */
export function geoEquirectangular(): GeoProjection;

/**
 * The raw equirectangular (plate carrée) projection.
 */
export function geoEquirectangularRaw(): GeoRawProjection;

/**
 * The spherical Mercator projection.
 * Defines a default projection.clipExtent such that the world is projected to a square, clipped to approximately ±85° latitude.
 */
export function geoMercator(): GeoProjection;
/**
 * The raw spherical Mercator projection.
 */
export function geoMercatorRaw(): GeoRawProjection;

/**
 * The transverse spherical Mercator projection.
 * Defines a default projection.clipExtent such that the world is projected to a square, clipped to approximately ±85° latitude.
 */
export function geoTransverseMercator(): GeoProjection;

/**
 * The raw transverse spherical Mercator projection.
 */
export function geoTransverseMercatorRaw(): GeoRawProjection;

/**
 * The Natural Earth projection is a pseudocylindrical projection designed by Tom Patterson. It is neither conformal nor equal-area, but appealing to the eye for small-scale maps of the whole world.
 */
export function geoNaturalEarth1(): GeoProjection;

/**
 * The raw pseudo-cylindircal Natural Earth projection.
 */
export function geoNaturalEarth1Raw(): GeoRawProjection;

// ----------------------------------------------------------------------
// Projection Transforms
// ----------------------------------------------------------------------

// geoTransform(...) ====================================================

/**
 * A Prototype interface which serves as a template for the implementation of a geometric transform using geoTransform(...)
 * It serves as a reference for the custom methods which can be passed into geoTransform as argument to crete a generalized
 * transform projection.
 */
export interface GeoTransformPrototype {
    /**
     * Indicates the end of a line or ring. Within a polygon, indicates the end of a ring.
     * Unlike GeoJSON, the redundant closing coordinate of a ring is not indicated via point, and instead is implied via lineEnd within a polygon.
     */
    lineEnd?(this: this & { stream: GeoStream }): void;
    /**
     * Indicates the start of a line or ring. Within a polygon, indicates the start of a ring. The first ring of a polygon is the exterior ring, and is typically clockwise.
     * Any subsequent rings indicate holes in the polygon, and are typically counterclockwise.
     */
    lineStart?(this: this & { stream: GeoStream }): void;
    /**
     * Indicates a point with the specified coordinates x and y (and optionally z). The coordinate system is unspecified and implementation-dependent;
     * for example, projection streams require spherical coordinates in degrees as input. Outside the context of a polygon or line,
     * a point indicates a point geometry object (Point or MultiPoint). Within a line or polygon ring, the point indicates a control point.
     *
     * @param x x-coordinate of point.
     * @param y y-coordinate of point.
     * @param z Optional z-coordinate of point.
     */
    point?(this: this & { stream: GeoStream }, x: number, y: number, z?: number): void;
    /**
     * Indicates the end of a polygon.
     */
    polygonEnd?(this: this & { stream: GeoStream }): void;
    /**
     * Indicates the start of a polygon. The first line of a polygon indicates the exterior ring, and any subsequent lines indicate interior holes.
     */
    polygonStart?(this: this & { stream: GeoStream }): void;
    /**
     * Indicates the sphere (the globe; the unit sphere centered at ⟨0,0,0⟩).
     */
    sphere?(this: this & { stream: GeoStream }): void;
}

// TODO: Review whether GeoStreamWrapper should be included into return value union type, i.e. ({ stream: (s: GeoStream) => (T & GeoStream & GeoStreamWrapper)})?
// It probably should be omitted for purposes of this API. The stream method added to (T & GeoStream) is more of a private member used internally to
// implement the Transform factory

/**
 * Defines an arbitrary transform using the methods defined on the specified methods object.
 * Any undefined methods will use pass-through methods that propagate inputs to the output stream.
 *
 * @param methods An object with custom method implementations, which are used to create a transform projection.
 */
export function geoTransform<T extends GeoTransformPrototype>(methods: T): { stream(s: GeoStream): T & GeoStream };

// geoIdentity() =================================================================

/**
 * @deprecated Misspelled name. Use GeoIdentityTransform.
 */
export type GeoIdentityTranform = GeoIdentityTransform;

/**
 * Geo Identity Transform
 */
export interface GeoIdentityTransform extends GeoStreamWrapper {
    /**
     * Returns a new array [x, y] (typically in pixels) representing the projected point of the given point.
     * The point must be specified as a two-element array [longitude, latitude] in degrees.
     * May return null if the specified point has no defined projected position, such as when the point is outside the clipping bounds of the projection.
     *
     * @param point A point specified as a two-dimensional array [longitude, latitude] in degrees.
     */
    (point: [number, number]): [number, number] | null;

    /**
     * Returns a new array [longitude, latitude] in degrees representing the unprojected point of the given projected point.
     * May return null if the specified point has no defined projected position, such as when the point is outside the clipping bounds of the projection.
     *
     * @param point The projected point, specified as a two-element array [x, y] (typically in pixels).
     */
    invert(point: [number, number]): [number, number] | null;

    /**
     * Returns the current cartesian clipping function.
     * Post-clipping occurs on the plane, when a projection is bounded to a certain extent such as a rectangle.
     */
    postclip(): (stream: GeoStream) => GeoStream;
    /**
     * Sets the projection’s cartesian clipping to the specified function and returns the projection.
     *
     * @param postclip A cartesian clipping function. Clipping functions are implemented as transformations of a projection stream.
     * Post-clipping operates on planar coordinates, in pixels.
     */
    postclip(postclip: (stream: GeoStream) => GeoStream): this;

    /**
     * Returns the current scale factor.
     *
     * The scale factor corresponds linearly to the distance between projected points; however, absolute scale factors are not equivalent across projections.
     */
    scale(): number;
    /**
     * Sets the projection’s scale factor to the specified value and returns the projection.
     * The scale factor corresponds linearly to the distance between projected points; however, absolute scale factors are not equivalent across projections.
     *
     * @param scale Scale factor to be used for the projection.
     */
    scale(scale: number): this;

    /**
     * Returns the current translation offset.
     * The translation offset determines the pixel coordinates of the projection’s center.
     */
    translate(): [number, number];
    /**
     * Sets the projection’s translation offset to the specified two-element array [tx, ty] and returns the projection.
     * The translation offset determines the pixel coordinates of the projection’s center.
     *
     * @param point A two-element array [tx, ty] specifying the translation offset.
     */
    translate(point: [number, number]): this;

    /**
     * Returns the projection’s current angle, which defaults to 0°.
     */
    angle(): number;
    /**
     * Sets the projection’s post-projection planar rotation angle to the specified angle in degrees and returns the projection.
     * @param angle The new rotation angle of the projection.
     */
    angle(angle: number): this;

    /**
     * Sets the projection’s scale and translate to fit the specified GeoJSON object in the center of the given extent.
     * The extent is specified as an array [[x₀, y₀], [x₁, y₁]], where x₀ is the left side of the bounding box, y₀ is the top, x₁ is the right and y₁ is the bottom. Returns the projection.
     */
    fitExtent(
        extent: [[number, number], [number, number]],
        object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
    ): this;

    /**
     * A convenience method for projection.fitExtent where the top-left corner of the extent is [0, 0].
     */
    fitSize(
        size: [number, number],
        object: ExtendedFeature | ExtendedFeatureCollection | GeoGeometryObjects | ExtendedGeometryCollection,
    ): this;

    /**
     * Returns the current viewport clip extent which defaults to null.
     */
    clipExtent(): [[number, number], [number, number]] | null;
    /**
     * Sets the projection’s viewport clip extent to the specified bounds in pixels and returns the projection.
     * The extent bounds are specified as an array [[x₀, y₀], [x₁, y₁]], where x₀ is the left-side of the viewport, y₀ is the top, x₁ is the right and y₁ is the bottom.
     * If extent is null, no viewport clipping is performed.
     */
    clipExtent(extent: null | [[number, number], [number, number]]): this;

    /**
     * Returns true if x-reflection is enabled, which defaults to false.
     */
    reflectX(): boolean;
    /**
     * Sets whether or not the x-dimension is reflected (negated) in the output.
     *
     * @param reflect true = reflect x-dimension, false = do not reflect x-dimension.
     */
    reflectX(reflect: boolean): this;

    /**
     * Returns true if y-reflection is enabled, which defaults to false.
     */
    reflectY(): boolean;
    /**
     * Sets whether or not the y-dimension is reflected (negated) in the output.
     *
     * This is especially useful for transforming from standard spatial reference systems,
     * which treat positive y as pointing up, to display coordinate systems such as Canvas and SVG,
     * which treat positive y as pointing down.
     *
     * @param reflect true = reflect y-dimension, false = do not reflect y-dimension.
     */
    reflectY(reflect: boolean): this;
}

/**
 * Returns the identity transform which can be used to scale, translate and clip planar geometry.
 */
export function geoIdentity(): GeoIdentityTransform;

// ----------------------------------------------------------------------
// Clipping Functions
// ----------------------------------------------------------------------

/**
 * A clipping function transforming a stream such that geometries (lines or polygons) that cross the antimeridian line are cut in two, one on each side.
 * Typically used for pre-clipping.
 */
export function geoClipAntimeridian(stream: GeoStream): GeoStream;

/**
 * Generates a clipping function transforming a stream such that geometries are bounded by a small circle of radius angle around the projection’s center.
 * Typically used for pre-clipping.
 *
 * @param angle A clipping angle.
 */
export function geoClipCircle(angle: number): (stream: GeoStream) => GeoStream;

/**
 * Generates a clipping function transforming a stream such that geometries are bounded by a rectangle of coordinates [[x0, y0], [x1, y1]].
 * Typically used for post-clipping.
 *
 * @param x0 x0 coordinate.
 * @param y0 y0 coordinate.
 * @param x1 x1 coordinate.
 * @param y1 y1 coordinate.
 */
export function geoClipRectangle(x0: number, y0: number, x1: number, y1: number): (stream: GeoStream) => GeoStream;
