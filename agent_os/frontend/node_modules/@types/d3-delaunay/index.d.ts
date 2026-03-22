/**
 * Delaunay triangulation
 */
export class Delaunay<P> {
    /**
     * Returns the Delaunay triangulation for the given flat array [x0, y0, x1, y1, …] of points.
     */
    constructor(points: ArrayLike<number>);

    /**
     * Returns the Delaunay triangulation for the given array or iterable of points where each point is an array in the form: [x, y].
     */
    static from(points: ArrayLike<Delaunay.Point> | Iterable<Delaunay.Point>): Delaunay<Delaunay.Point>;
    /**
     * Returns the Delaunay triangulation for the given array or iterable of points.
     * Otherwise, the getX and getY functions are invoked for each point in order, and must return the respective x- and y-coordinate for each point.
     * If that is specified, the functions getX and getY are invoked with that as this.
     * (See Array.from for reference.)
     */
    static from<P>(
        points: ArrayLike<P> | Iterable<P>,
        getX: Delaunay.GetCoordinate<P, ArrayLike<P> | Iterable<P>>,
        getY: Delaunay.GetCoordinate<P, ArrayLike<P> | Iterable<P>>,
        that?: any,
    ): Delaunay<P>;

    /**
     * The coordinates of the points as an array [x0, y0, x1, y1, ...].
     * Typically, this is a Float64Array, however you can use any array-like type in the constructor.
     */
    points: ArrayLike<number>;

    /**
     * The halfedge indices as an Int32Array [j0, j1, ...].
     * For each index 0 <= i < halfedges.length, there is a halfedge from triangle vertex j = halfedges[i] to triangle vertex i.
     */
    halfedges: Int32Array;

    /**
     * An Int32Array of point indexes that form the convex hull in counterclockwise order.
     * If the points are collinear, returns them ordered.
     */
    hull: Uint32Array;

    /**
     * The triangle vertex indices as an Uint32Array [i0, j0, k0, i1, j1, k1, ...].
     * Each contiguous triplet of indices i, j, k forms a counterclockwise triangle.
     * The coordinates of the triangle's points can be found by going through 'points'.
     */
    triangles: Uint32Array;

    /**
     * The incoming halfedge indexes as a Int32Array [e0, e1, e2, ...].
     * For each point i, inedges[i] is the halfedge index e of an incoming halfedge.
     * For coincident points, the halfedge index is -1; for points on the convex hull, the incoming halfedge is on the convex hull; for other points, the choice of incoming halfedge is arbitrary.
     */
    inedges: Int32Array;

    /**
     * Returns the index of the input point that is closest to the specified point ⟨x, y⟩.
     * The search is started at the specified point i. If i is not specified, it defaults to zero.
     */
    find(x: number, y: number, i?: number): number;

    /**
     * Returns an iterable over the indexes of the neighboring points to the specified point i.
     * The iterable is empty if i is a coincident point.
     */
    neighbors(i: number): IterableIterator<number>;

    /**
     * Renders the edges of the Delaunay triangulation to an SVG path string.
     */
    render(): string;
    /**
     * Renders the edges of the Delaunay triangulation to the specified context.
     * The specified context must implement the context.moveTo and context.lineTo methods from the CanvasPathMethods API.
     */
    render(context: Delaunay.MoveContext & Delaunay.LineContext): void;

    /**
     * Renders the convex hull of the Delaunay triangulation to an SVG path string.
     */
    renderHull(): string;
    /**
     * Renders the convex hull of the Delaunay triangulation to the specified context.
     * The specified context must implement the context.moveTo and context.lineTo methods from the CanvasPathMethods API.
     */
    renderHull(context: Delaunay.MoveContext & Delaunay.LineContext): void;

    /**
     * Renders triangle i of the Delaunay triangulation to an SVG path string.
     */
    renderTriangle(i: number): string;
    /**
     * Renders triangle i of the Delaunay triangulation to the specified context.
     * The specified context must implement the context.moveTo, context.lineTo and context.closePath methods from the CanvasPathMethods API.
     */
    renderTriangle(i: number, context: Delaunay.MoveContext & Delaunay.LineContext & Delaunay.ClosableContext): void;

    /**
     * Renders the input points of the Delaunay triangulation to an SVG path string as circles with radius 2.
     */
    renderPoints(): string;
    /**
     * Renders the input points of the Delaunay triangulation to an SVG path string as circles with the specified radius.
     */
    renderPoints(context: undefined, radius: number): string;
    /**
     * Renders the input points of the Delaunay triangulation to the specified context as circles with the specified radius.
     * If radius is not specified, it defaults to 2.
     * The specified context must implement the context.moveTo and context.arc methods from the CanvasPathMethods API.
     */
    renderPoints(context: Delaunay.MoveContext & Delaunay.ArcContext, radius?: number): void;

    /**
     * Returns the closed polygon [[x0, y0], [x1, y1], ..., [x0, y0]] representing the convex hull.
     */
    hullPolygon(): Delaunay.Polygon;

    /**
     * Returns the closed polygon [[x0, y0], [x1, y1], [x2, y2], [x0, y0]] representing the triangle i.
     */
    trianglePolygon(i: number): Delaunay.Triangle;
    /**
     * Returns an iterable over the polygons for each triangle, in order.
     */
    trianglePolygons(): IterableIterator<Delaunay.Triangle>;

    /**
     * Updates the triangulation after the points have been modified in-place.
     */
    update(): this;

    /**
     * Returns the Voronoi diagram for the associated points.
     * When rendering, the diagram will be clipped to the specified bounds = [xmin, ymin, xmax, ymax].
     * If bounds is not specified, it defaults to [0, 0, 960, 500].
     * See To Infinity and Back Again for an interactive explanation of Voronoi cell clipping.
     */
    voronoi(bounds?: Delaunay.Bounds): Voronoi<P>;
}

export namespace Delaunay {
    /**
     * A point represented as an array tuple [x, y].
     */
    type Point = [number, number];

    /**
     * A closed polygon [[x0, y0], [x1, y1], [x2, y2], [x0, y0]] representing a triangle.
     */
    type Triangle = Point[];

    /**
     * A closed polygon [[x0, y0], [x1, y1], ..., [x0, y0]].
     */
    type Polygon = Point[];

    /**
     * A rectangular area [x, y, width, height].
     */
    type Bounds = [number, number, number, number];

    /**
     * A function to extract a x- or y-coordinate from the specified point.
     */
    type GetCoordinate<P, PS> = (point: P, i: number, points: PS) => number;

    /**
     * An interface for the rect() method of the CanvasPathMethods API.
     */
    interface RectContext {
        /**
         * rect() method of the CanvasPathMethods API.
         */
        rect(x: number, y: number, width: number, height: number): void;
    }

    /**
     * An interface for the moveTo() method of the CanvasPathMethods API.
     */
    interface MoveContext {
        /**
         * moveTo() method of the CanvasPathMethods API.
         */
        moveTo(x: number, y: number): void;
    }

    /**
     * An interface for the lineTo() method of the CanvasPathMethods API.
     */
    interface LineContext {
        /**
         * lineTo() method of the CanvasPathMethods API.
         */
        lineTo(x: number, y: number): void;
    }

    /**
     * An interface for the arc() method of the CanvasPathMethods API.
     */
    interface ArcContext {
        /**
         * arc() method of the CanvasPathMethods API.
         */
        arc(
            x: number,
            y: number,
            radius: number,
            startAngle: number,
            endAngle: number,
            counterclockwise?: boolean,
        ): void;
    }

    /**
     * An interface for the closePath() method of the CanvasPathMethods API.
     */
    interface ClosableContext {
        /**
         * closePath() method of the CanvasPathMethods API.
         */
        closePath(): void;
    }
}

/**
 * Voronoi regions
 */
export class Voronoi<P> {
    /**
     * The Voronoi diagram’s associated Delaunay triangulation.
     */
    delaunay: Delaunay<P>;

    /**
     * The circumcenters of the Delaunay triangles [cx0, cy0, cx1, cy1, ...].
     * Each contiguous pair of coordinates cx, cy is the circumcenter for the corresponding triangle.
     * These circumcenters form the coordinates of the Voronoi cell polygons.
     */
    circumcenters: Float64Array;

    /**
     * An array [vx0, vy0, wx0, wy0, ...] where each non-zero quadruple describes an open (infinite) cell
     * on the outer hull, giving the directions of two open half-lines.
     */
    vectors: Float64Array;

    /**
     * The bounds of the viewport [xmin, ymin, xmax, ymax] for rendering the Voronoi diagram.
     * These values only affect the rendering methods (voronoi.render, voronoi.renderBounds, cell.render).
     */
    xmin: number;
    ymin: number;
    xmax: number;
    ymax: number;

    /**
     * Returns true if the cell with the specified index i contains the specified point ⟨x, y⟩.
     * (This method is not affected by the associated Voronoi diagram’s viewport bounds.)
     */
    contains(i: number, x: number, y: number): boolean;

    /**
     * Returns an iterable over the indexes of the cells that share a common edge with the specified cell i.
     * Voronoi neighbors are always neighbors on the Delaunay graph, but the converse is false when the common edge has been clipped out by the Voronoi diagram’s viewport.
     */
    neighbors(i: number): Iterable<number>;

    /**
     * Renders the mesh of Voronoi cells to an SVG path string.
     */
    render(): string;
    /**
     * Renders the mesh of Voronoi cells to the specified context.
     * The specified context must implement the context.moveTo and context.lineTo methods from the CanvasPathMethods API.
     */
    render(context: Delaunay.MoveContext & Delaunay.LineContext): void;

    /**
     * Renders the viewport extent to an SVG path string.
     */
    renderBounds(): string;
    /**
     * Renders the viewport extent to the specified context.
     * The specified context must implement the context.rect method from the CanvasPathMethods API.
     * Equivalent to context.rect(voronoi.xmin, voronoi.ymin, voronoi.xmax - voronoi.xmin, voronoi.ymax - voronoi.ymin).
     */
    renderBounds(context: Delaunay.RectContext): void;

    /**
     * Renders the cell with the specified index i to an SVG path string.
     */
    renderCell(i: number): string;
    /**
     * Renders the cell with the specified index i to the specified context.
     * The specified context must implement the context.moveTo, context.lineTo, and context.closePath methods from the CanvasPathMethods API.
     */
    renderCell(i: number, context: Delaunay.MoveContext & Delaunay.LineContext & Delaunay.ClosableContext): void;

    /**
     * Returns an iterable over the non-empty polygons for each cell, with the cell index as property.
     */
    cellPolygons(): IterableIterator<Delaunay.Polygon & { index: number }>;

    /**
     * Returns the convex, closed polygon [[x0, y0], [x1, y1], ..., [x0, y0]] representing the cell for the specified point i.
     */
    cellPolygon(i: number): Delaunay.Polygon;

    /**
     * Updates the Voronoi diagram and underlying triangulation after the points have been modified in-place — useful for Lloyd’s relaxation.
     */
    update(): this;
}
