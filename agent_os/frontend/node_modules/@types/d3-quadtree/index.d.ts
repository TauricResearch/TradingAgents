// Last module patch version validated against: 3.0.1

/**
 * Leaf node of the quadtree.
 */
export interface QuadtreeLeaf<T> {
    /**
     * The data associated with this point, as passed to quadtree.add.
     */
    data: T;

    /**
     * The next datum in this leaf, if any.
     */
    next?: QuadtreeLeaf<T> | undefined;

    /**
     * The length property may be used to distinguish leaf nodes from internal nodes: it is undefined for leaf nodes, and 4 for internal nodes.
     */
    length?: undefined;
}

/**
 * Internal nodes of the quadtree are represented as four-element arrays in left-to-right, top-to-bottom order:
 *
 * 0 - the top-left quadrant, if any.
 * 1 - the top-right quadrant, if any.
 * 2 - the bottom-left quadrant, if any.
 * 3 - the bottom-right quadrant, if any.
 *
 * A child quadrant may be undefined if it is empty.
 */
export interface QuadtreeInternalNode<T> extends Array<QuadtreeInternalNode<T> | QuadtreeLeaf<T> | undefined> {
    /**
     * The length property may be used to distinguish leaf nodes from internal nodes: it is undefined for leaf nodes, and 4 for internal nodes.
     */
    length: 4;
}

export interface Quadtree<T> {
    /**
     * Returns the current x-accessor, which defaults to: `x(d) => d[0]`.
     */
    x(): (d: T) => number;
    /**
     * Sets the current x-coordinate accessor and returns the quadtree.
     * The x-accessors must be consistent, returning the same value given the same input.
     *
     * @param x The x-coordinate accessor.
     */
    x(x: (d: T) => number): this;

    /**
     * Returns the current y-accessor, which defaults to: `y(d) => d[1]`.
     */
    y(): (d: T) => number;
    /**
     * Sets the current y-coordinate accessor and returns the quadtree.
     * The y-accessors must be consistent, returning the same value given the same input.
     *
     * @param y The y-coordinate accessor.
     */
    y(y: (d: T) => number): this;

    /**
     * Returns the quadtree's current extent `[[x0, y0], [x1, y1]]`,
     * where `x0` and `y0` are the inclusive lower bounds and `x1` and `y1` are the inclusive upper bounds,
     * or `undefined` if the quadtree has no extent.
     */
    extent(): [[number, number], [number, number]] | undefined;
    /**
     * Expands the quadtree to cover the specified points `[[x0, y0], [x1, y1]]` and returns the quadtree.
     * The extent may also be expanded by calling `quadtree.cover` or `quadtree.add`.
     *
     * @param extend The specified points to cover.
     */
    extent(extend: [[number, number], [number, number]]): this;

    /**
     * Expands the quadtree to cover the specified point ⟨x,y⟩, and returns the quadtree.
     * * If the quadtree’s extent already covers the specified point, this method does nothing.
     * * If the quadtree has an extent, the extent is repeatedly doubled to cover the specified point, wrapping the root node as necessary.
     * * If the quadtree is empty, the extent is initialized to the extent `[[⌊x⌋, ⌊y⌋], [⌈x⌉, ⌈y⌉]]`.
     * Rounding is necessary such that if the extent is later doubled, the boundaries of existing quadrants do not change due to floating point error.
     *
     * @param x The x-coordinate for the specified point to cover.
     * @param y The y-coordinate for the specified point to cover.
     */
    cover(x: number, y: number): this;

    /**
     * Adds the specified datum to the quadtree, deriving its coordinates ⟨x,y⟩ using the current x- and y-accessors, and returns the quadtree.
     * If the new point is outside the current extent of the quadtree, the quadtree is automatically expanded to cover the new point.
     *
     * @param datum The specified datum to add.
     */
    add(datum: T): this;

    /**
     * Adds the specified array of data to the quadtree, deriving each element’s coordinates ⟨x,y⟩ using the current x- and y-accessors, and return this quadtree.
     * This is approximately equivalent to calling quadtree.add repeatedly.
     * However, this method results in a more compact quadtree because the extent of the data is computed first before adding the data.
     *
     * @param data The specified array of data to add.
     */
    addAll(data: T[]): this;

    /**
     * Removes the specified datum to the quadtree, deriving its coordinates ⟨x,y⟩ using the current x- and y-accessors, and returns the quadtree.
     * If the specified datum does not exist in this quadtree, this method does nothing.
     *
     * @param datum The specified datum to remove.
     */
    remove(datum: T): this;

    /**
     * Removes the specified data to the quadtree, deriving their coordinates ⟨x,y⟩ using the current x- and y-accessors, and returns the quadtree.
     * If a specified datum does not exist in this quadtree, it is ignored.
     *
     * @param data The specified array of data to remove.
     */
    removeAll(data: T[]): this;

    /**
     * Returns a copy of the quadtree. All nodes in the returned quadtree are identical copies of the corresponding node in the quadtree;
     * however, any data in the quadtree is shared by reference and not copied.
     */
    copy(): Quadtree<T>;

    /**
     * Returns the root node of the quadtree.
     */
    root(): QuadtreeInternalNode<T> | QuadtreeLeaf<T>;

    /**
     * Returns an array of all data in the quadtree.
     */
    data(): T[];

    /**
     * Returns the total number of data in the quadtree.
     */
    size(): number;

    /**
     * Returns the datum closest to the position ⟨x,y⟩ with the given search radius. If radius is not specified, it defaults to infinity.
     * If there is no datum within the search area, returns undefined.
     *
     * @param x The x-coordinate for the search position.
     * @param y The y-coordinate for the search position.
     * @param radius The optional search radius.
     */
    find(x: number, y: number, radius?: number): T | undefined;

    /**
     * Visits each node in the quadtree in pre-order traversal, invoking the specified callback with arguments `node`, `x0`, `y0`, `x1`, `y1` for each node,
     * where `node` is the node being visited, ⟨x0, y0⟩ are the lower bounds of the node, and ⟨x1, y1⟩ are the upper bounds, and returns the quadtree.
     *
     * If the callback returns true for a given node, then the children of that node are not visited; otherwise, all child nodes are visited.
     * This can be used to quickly visit only parts of the tree.
     * Note, however, that child quadrants are always visited in sibling order: top-left, top-right, bottom-left, bottom-right.
     * In cases such as search, visiting siblings in a specific order may be faster.
     *
     * @param callback The callback invoked for each node.
     */
    visit(
        callback: (
            node: QuadtreeInternalNode<T> | QuadtreeLeaf<T>,
            x0: number,
            y0: number,
            x1: number,
            y1: number,
            // eslint-disable-next-line @typescript-eslint/no-invalid-void-type
        ) => void | boolean,
    ): this;

    /**
     * Visits each node in the quadtree in post-order traversal, invoking the specified callback with arguments `node`, `x0`, `y0`, `x1`, `y1` for each node,
     * where `node` is the node being visited, ⟨x0, y0⟩ are the lower bounds of the node, and ⟨x1, y1⟩ are the upper bounds, and returns the quadtree.
     *
     * @param callback The callback invoked for each node.
     */
    visitAfter(
        callback: (
            node: QuadtreeInternalNode<T> | QuadtreeLeaf<T>,
            x0: number,
            y0: number,
            x1: number,
            y1: number,
        ) => void,
    ): this;
}

/**
 * Creates a new, empty quadtree with an empty extent and the default x- and y-accessors.
 * If data is specified, adds the specified array of data to the quadtree.
 */
export function quadtree<T = [number, number]>(data?: T[]): Quadtree<T>;
/**
 * Creates a new, empty quadtree with an empty extent and the default x- and y-accessors.
 * Adds the specified array of data to the quadtree.
 * Sets the x- and y- accessors to the specified functions before adding the specified array of data to the quadtree.
 */
export function quadtree<T = [number, number]>(data: T[], x: (d: T) => number, y: (d: T) => number): Quadtree<T>;
