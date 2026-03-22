// Last module patch version validated against: 3.1.0

/**
 * A D3 path serializer implementing CanvasPathMethods
 */
export interface Path {
    /**
     * Move to the specified point ⟨x, y⟩. Equivalent to context.moveTo and SVG’s “moveto” command.
     *
     * @param x x-Coordinate of point to move to
     * @param y y-Coordinate of point to move to
     */
    moveTo(x: number, y: number): void;

    /**
     * Ends the current subpath and causes an automatic straight line to be drawn from the current point to the initial point of the current subpath.
     * Equivalent to context.closePath and SVG’s “closepath” command.
     */
    closePath(): void;

    /**
     * Draws a straight line from the current point to the specified point ⟨x, y⟩.
     * Equivalent to context.lineTo and SVG’s “lineto” command.
     *
     * @param x x-Coordinate of point to draw the line to
     * @param y y-Coordinate of point to draw the line to
     */
    lineTo(x: number, y: number): void;

    /**
     * Draws a quadratic Bézier segment from the current point to the specified point ⟨x, y⟩, with the specified control point ⟨cpx, cpy⟩.
     * Equivalent to context.quadraticCurveTo and SVG’s quadratic Bézier curve commands.
     *
     * @param cpx x-Coordinate of the control point for the quadratic Bézier curve
     * @param cpy y-Coordinate of the control point for the quadratic Bézier curve
     * @param x x-Coordinate of point to draw the curve to
     * @param y y-Coordinate of point to draw the curve to
     */
    quadraticCurveTo(cpx: number, cpy: number, x: number, y: number): void;

    /**
     * Draws a cubic Bézier segment from the current point to the specified point ⟨x, y⟩, with the specified control points ⟨cpx1, cpy1⟩ and ⟨cpx2, cpy2⟩.
     * Equivalent to context.bezierCurveTo and SVG’s cubic Bézier curve commands.
     *
     * @param cpx1 x-Coordinate of the first control point for the Bézier curve
     * @param cpy1 y-Coordinate of the first control point for the Bézier curve
     * @param cpx2 x-Coordinate of the second control point for the Bézier curve
     * @param cpy2 y-Coordinate of the second control point for the Bézier curve
     * @param x x-Coordinate of point to draw the curve to
     * @param y y-Coordinate of point to draw the curve to
     */
    bezierCurveTo(cpx1: number, cpy1: number, cpx2: number, cpy2: number, x: number, y: number): void;

    /**
     * Draws a circular arc segment with the specified radius that starts tangent to the line between the current point and the specified point ⟨x1, y1⟩
     * and ends tangent to the line between the specified points ⟨x1, y1⟩ and ⟨x2, y2⟩. If the first tangent point is not equal to the current point,
     * a straight line is drawn between the current point and the first tangent point. Equivalent to context.arcTo and uses SVG’s elliptical arc curve commands.
     *
     * @param x1 x-Coordinate of the first tangent point
     * @param y1 y-Coordinate of the first tangent point
     * @param x2 x-Coordinate of the second tangent point
     * @param y2 y-Coordinate of the second tangent point
     * @param radius  Radius of the arc segment
     */
    arcTo(x1: number, y1: number, x2: number, y2: number, radius: number): void;

    /**
     * Draws a circular arc segment with the specified center ⟨x, y⟩, radius, startAngle and endAngle. If anticlockwise is true,
     * the arc is drawn in the anticlockwise direction; otherwise, it is drawn in the clockwise direction.
     * If the current point is not equal to the starting point of the arc, a straight line is drawn from the current point to the start of the arc.
     * Equivalent to context.arc and uses SVG’s elliptical arc curve commands.
     *
     * @param x x-Coordinate of the center point of the arc segment
     * @param y y-Coordinate of the center point of the arc segment
     * @param radius Radius of the arc segment
     * @param startAngle Start angle of arc segment
     * @param endAngle End angle of arc segment
     * @param anticlockwise Flag indicating directionality (true = anti-clockwise, false = clockwise)
     */
    arc(x: number, y: number, radius: number, startAngle: number, endAngle: number, anticlockwise?: boolean): void;

    /**
     * Creates a new subpath containing just the four points ⟨x, y⟩, ⟨x + w, y⟩, ⟨x + w, y + h⟩, ⟨x, y + h⟩,
     * with those four points connected by straight lines, and then marks the subpath as closed. Equivalent to context.rect and uses SVG’s “lineto” commands.
     *
     * @param x x-Coordinate of starting point for drawing the rectangle
     * @param y y-Coordinate of starting point for drawing the rectangle
     * @param w Width of rectangle
     * @param h Height of rectangle
     */
    rect(x: number, y: number, w: number, h: number): void;

    /**
     * Returns the string representation of this path according to SVG’s path data specification.
     */
    toString(): string;
}

/**
 * Construct a D3 Path serializer
 */
export function path(): Path;

/**
 * Like {@link path}, except limits the digits after the decimal to the specified number of digits.
 * Useful for reducing the size of generated SVG path data.
 */
export function pathRound(digits?: number): Path;
