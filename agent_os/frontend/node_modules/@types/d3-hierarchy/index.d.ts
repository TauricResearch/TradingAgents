// Last module patch version validated against: 3.1.2

// -----------------------------------------------------------------------
// Hierarchy
// -----------------------------------------------------------------------

export interface HierarchyLink<Datum> {
    /**
     * The source of the link.
     */
    source: HierarchyNode<Datum>;

    /**
     * The target of the link.
     */
    target: HierarchyNode<Datum>;
}

export interface HierarchyNode<Datum> {
    new(data: Datum): this;

    /**
     * The associated data, as specified to the constructor.
     */
    data: Datum;

    /**
     * Zero for the root node, and increasing by one for each descendant generation.
     */
    readonly depth: number;

    /**
     * Zero for leaf nodes, and the greatest distance from any descendant leaf for internal nodes.
     */
    readonly height: number;

    /**
     * The parent node, or null for the root node.
     */
    parent: this | null;

    /**
     * An array of child nodes, if any; undefined for leaf nodes.
     */
    children?: this[] | undefined;

    /**
     * Aggregated numeric value as calculated by `sum(value)` or `count()`, if previously invoked.
     */
    readonly value?: number | undefined;

    /**
     * Optional node id string set by `StratifyOperator`, if hierarchical data was created from tabular data using stratify().
     */
    readonly id?: string | undefined;

    /**
     * The x position of this node. Set after a tree has been laid out by `tree` or `cluster`.
     *
     * ```
     * const root = d3.hierarchy(datum);
     * const treeLayout = d3.tree();
     * treeLayout(root);
     * // x and y are now set on root and its descendants
     * ```
     */
    x?: number | undefined;

    /**
     * The y position of this node. Set after a tree has been laid out by `tree` or `cluster`.
     *
     * ```
     * const root = d3.hierarchy(datum);
     * const treeLayout = d3.tree();
     * treeLayout(root);
     * // x and y are now set on root and its descendants
     * ```
     */
    y?: number | undefined;

    /**
     * Returns the array of ancestors nodes, starting with this node, then followed by each parent up to the root.
     */
    ancestors(): this[];

    /**
     * Returns the array of descendant nodes, starting with this node, then followed by each child in topological order.
     */
    descendants(): this[];

    /**
     * Returns the array of leaf nodes in traversal order; leaves are nodes with no children.
     */
    leaves(): this[];

    /**
     * Returns the first node in the hierarchy from this node for which the specified filter returns a truthy value. undefined if no such node is found.
     * @param filter Filter.
     */
    find(filter: (node: this) => boolean): this | undefined;

    /**
     * Returns the shortest path through the hierarchy from this node to the specified target node.
     * The path starts at this node, ascends to the least common ancestor of this node and the target node, and then descends to the target node.
     *
     * @param target The target node.
     */
    path(target: this): this[];

    /**
     * Returns an array of links for this node, where each link is an object that defines source and target properties.
     * The source of each link is the parent node, and the target is a child node.
     */
    links(): Array<HierarchyLink<Datum>>;

    /**
     * Evaluates the specified value function for this node and each descendant in post-order traversal, and returns this node.
     * The `node.value` property of each node is set to the numeric value returned by the specified function plus the combined value of all descendants.
     *
     * @param value The value function is passed the node’s data, and must return a non-negative number.
     */
    sum(value: (d: Datum) => number): this;

    /**
     * Computes the number of leaves under this node and assigns it to `node.value`, and similarly for every descendant of node.
     * If this node is a leaf, its count is one. Returns this node.
     */
    count(): this;

    /**
     * Sorts the children of this node, if any, and each of this node’s descendants’ children,
     * in pre-order traversal using the specified compare function, and returns this node.
     *
     * @param compare The compare function is passed two nodes a and b to compare.
     * If a should be before b, the function must return a value less than zero;
     * if b should be before a, the function must return a value greater than zero;
     * otherwise, the relative order of a and b are not specified. See `array.sort` for more.
     */
    sort(compare: (a: this, b: this) => number): this;

    /**
     * Returns an iterator over the node’s descendants in breadth-first order.
     */
    [Symbol.iterator](): Iterator<this>;

    /**
     * Invokes the specified function for node and each descendant in breadth-first order,
     * such that a given node is only visited if all nodes of lesser depth have already been visited,
     * as well as all preceding nodes of the same depth.
     *
     * @param func The specified function is passed the current descendant, the zero-based traversal index, and this node.
     * @param that If that is specified, it is the this context of the callback.
     */
    each<T = undefined>(func: (this: T, node: this, index: number, thisNode: this) => void, that?: T): this;

    /**
     * Invokes the specified function for node and each descendant in post-order traversal,
     * such that a given node is only visited after all of its descendants have already been visited.
     *
     * @param func The specified function is passed the current descendant, the zero-based traversal index, and this node.
     * @param that If that is specified, it is the this context of the callback.
     */
    eachAfter<T = undefined>(func: (this: T, node: this, index: number, thisNode: this) => void, that?: T): this;

    /**
     * Invokes the specified function for node and each descendant in pre-order traversal,
     * such that a given node is only visited after all of its ancestors have already been visited.
     *
     * @param func The specified function is passed the current descendant, the zero-based traversal index, and this node.
     * @param that If that is specified, it is the this context of the callback.
     */
    eachBefore<T = undefined>(func: (this: T, node: this, index: number, thisNode: this) => void, that?: T): this;

    /**
     * Return a deep copy of the subtree starting at this node. The returned deep copy shares the same data, however.
     * The returned node is the root of a new tree; the returned node’s parent is always null and its depth is always zero.
     */
    copy(): this;
}

/**
 * Constructs a root node from the specified hierarchical data.
 *
 * @param data The root specified data.
 * If *data* is a Map, it is implicitly converted to the entry [undefined, *data*],
 * and the children accessor instead defaults to `(d) => Array.isArray(d) ? d[1] : null;`.
 * @param children The specified children accessor function is invoked for each datum, starting with the root data,
 * and must return an iterable of data representing the children, if any.
 * If children is not specified, it defaults to: `(d) => d.children`.
 */
export function hierarchy<Datum>(
    data: Datum,
    children?: (d: Datum) => Iterable<Datum> | null | undefined,
): HierarchyNode<Datum>;

// -----------------------------------------------------------------------
// Stratify
// -----------------------------------------------------------------------

export interface StratifyOperator<Datum> {
    /**
     * Generates a new hierarchy from the specified tabular data. Each node in the returned object has a shallow copy of the properties
     * from the corresponding data object, excluding the following reserved properties: id, parentId, children.
     *
     * @param data The root specified data.
     * @throws Error on missing id, ambiguous id, cycle, multiple roots or no root.
     */
    (data: Datum[]): HierarchyNode<Datum>;

    /**
     * Returns the current id accessor, which defaults to: `(d) => d.id`.
     */
    id(): (d: Datum, i: number, data: Datum[]) => string | null | "" | undefined;
    /**
     * Sets the id accessor to the given function.
     * The id accessor is invoked for each element in the input data passed to the stratify operator.
     * The returned string is then used to identify the node's relationships in conjunction with the parent id.
     * For leaf nodes, the id may be undefined, null or the empty string; otherwise, the id must be unique.
     *
     * @param id The id accessor.
     */
    id(id: (d: Datum, i: number, data: Datum[]) => string | null | "" | undefined): this;

    /**
     * Returns the current parent id accessor, which defaults to: `(d) => d.parentId`.
     */
    parentId(): (d: Datum, i: number, data: Datum[]) => string | null | "" | undefined;
    /**
     * Sets the parent id accessor to the given function.
     * The parent id accessor is invoked for each element in the input data passed to the stratify operator.
     * The returned string is then used to identify the node's relationships in conjunction with the id.
     * For the root node, the parent id should be undefined, null or the empty string.
     * There must be exactly one root node in the input data, and no circular relationships.
     *
     * @param parentId The parent id accessor.
     */
    parentId(parentId: (d: Datum, i: number, data: Datum[]) => string | null | "" | undefined): this;

    /**
     * Returns the current path accessor, which defaults to undefined.
     */
    path(): ((d: Datum, i: number, data: Datum[]) => string) | null | undefined;
    /**
     * If path is specified, sets the path accessor to the given function and returns this stratify operator.
     * Otherwise, returns the current path accessor, which defaults to undefined.
     * If a path accessor is set, the id and parentId arguments are ignored,
     * and a unix-like hierarchy is computed on the slash-delimited strings
     * returned by the path accessor, imputing parent nodes and ids as necessary.
     *
     * @param path The path accessor.
     */
    path(path: ((d: Datum, i: number, data: Datum[]) => string) | null | undefined): this;
}

/**
 * Constructs a new stratify operator with the default settings.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function stratify<Datum>(): StratifyOperator<Datum>;

// -----------------------------------------------------------------------
// Cluster
// -----------------------------------------------------------------------

export interface HierarchyPointLink<Datum> {
    /**
     * The source of the link.
     */
    source: HierarchyPointNode<Datum>;

    /**
     * The target of the link.
     */
    target: HierarchyPointNode<Datum>;
}

export interface HierarchyPointNode<Datum> extends HierarchyNode<Datum> {
    /**
     * The x-coordinate of the node.
     */
    x: number;

    /**
     * The y-coordinate of the node.
     */
    y: number;

    /**
     * Returns an array of links for this node, where each link is an object that defines source and target properties.
     * The source of each link is the parent node, and the target is a child node.
     */
    links(): Array<HierarchyPointLink<Datum>>;
}

export interface ClusterLayout<Datum> {
    /**
     * Lays out the specified root hierarchy.
     * You may want to call `root.sort` before passing the hierarchy to the cluster layout.
     *
     * @param root The specified root hierarchy.
     */
    (root: HierarchyNode<Datum>): HierarchyPointNode<Datum>;

    /**
     * Returns the current layout size, which defaults to [1, 1]. A layout size of null indicates that a node size will be used instead.
     */
    size(): [number, number] | null;
    /**
     * Sets this cluster layout’s size to the specified [width, height] array and returns the cluster layout.
     * The size represent an arbitrary coordinate system; for example, to produce a radial layout,
     * a size of [360, radius] corresponds to a breadth of 360° and a depth of radius.
     *
     * @param size The specified two-element size array.
     */
    size(size: [number, number]): this;

    /**
     * Returns the current node size, which defaults to null. A node size of null indicates that a layout size will be used instead.
     */
    nodeSize(): [number, number] | null;
    /**
     * Sets this cluster layout’s node size to the specified [width, height] array and returns this cluster layout.
     * When a node size is specified, the root node is always positioned at <0, 0>.
     *
     * @param size The specified two-element size array.
     */
    nodeSize(size: [number, number]): this;

    /**
     * Returns the current separation accessor, which defaults to: `(a, b) => a.parent == b.parent ? 1 : 2`.
     */
    separation(): (a: HierarchyPointNode<Datum>, b: HierarchyPointNode<Datum>) => number;
    /**
     * Sets the separation accessor to the specified function and returns this cluster layout.
     * The separation accessor is used to separate neighboring leaves.
     *
     * @param separation The separation function is passed two leaves a and b, and must return the desired separation.
     * The nodes are typically siblings, though the nodes may be more distantly related if the layout decides to place such nodes adjacent.
     */
    separation(separation: (a: HierarchyPointNode<Datum>, b: HierarchyPointNode<Datum>) => number): this;
}

/**
 * Creates a new cluster layout with default settings.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function cluster<Datum>(): ClusterLayout<Datum>;

// -----------------------------------------------------------------------
// Tree
// -----------------------------------------------------------------------

export interface TreeLayout<Datum> {
    /**
     * Lays out the specified root hierarchy.
     * You may want to call `root.sort` before passing the hierarchy to the tree layout.
     *
     * @param root The specified root hierarchy.
     */
    (root: HierarchyNode<Datum>): HierarchyPointNode<Datum>;

    /**
     * Returns the current layout size, which defaults to [1, 1]. A layout size of null indicates that a node size will be used instead.
     */
    size(): [number, number] | null;
    /**
     * Sets this tree layout’s size to the specified [width, height] array and returns the tree layout.
     * The size represent an arbitrary coordinate system; for example, to produce a radial layout,
     * a size of [360, radius] corresponds to a breadth of 360° and a depth of radius.
     *
     * @param size The specified two-element size array.
     */
    size(size: [number, number]): this;

    /**
     * Returns the current node size, which defaults to null. A node size of null indicates that a layout size will be used instead.
     */
    nodeSize(): [number, number] | null;
    /**
     * Sets this tree layout’s node size to the specified [width, height] array and returns this tree layout.
     * When a node size is specified, the root node is always positioned at <0, 0>.
     *
     * @param size The specified two-element size array.
     */
    nodeSize(size: [number, number]): this;

    /**
     * Returns the current separation accessor, which defaults to: `(a, b) => a.parent == b.parent ? 1 : 2`.
     */
    separation(): (a: HierarchyPointNode<Datum>, b: HierarchyPointNode<Datum>) => number;
    /**
     * Sets the separation accessor to the specified function and returns this tree layout.
     * The separation accessor is used to separate neighboring nodes.
     *
     * @param separation The separation function is passed two nodes a and b, and must return the desired separation.
     * The nodes are typically siblings, though the nodes may be more distantly related if the layout decides to place such nodes adjacent.
     */
    separation(separation: (a: HierarchyPointNode<Datum>, b: HierarchyPointNode<Datum>) => number): this;
}

/**
 * Creates a new tree layout with default settings.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function tree<Datum>(): TreeLayout<Datum>;

// -----------------------------------------------------------------------
// Treemap
// -----------------------------------------------------------------------

export interface HierarchyRectangularLink<Datum> {
    /**
     * The source of the link.
     */
    source: HierarchyRectangularNode<Datum>;

    /**
     * The target of the link.
     */
    target: HierarchyRectangularNode<Datum>;
}

export interface HierarchyRectangularNode<Datum> extends HierarchyNode<Datum> {
    /**
     * The left edge of the rectangle.
     */
    x0: number;

    /**
     * The top edge of the rectangle
     */
    y0: number;

    /**
     * The right edge of the rectangle.
     */
    x1: number;

    /**
     * The bottom edge of the rectangle.
     */
    y1: number;

    /**
     * Returns an array of links for this node, where each link is an object that defines source and target properties.
     * The source of each link is the parent node, and the target is a child node.
     */
    links(): Array<HierarchyRectangularLink<Datum>>;
}

export interface TreemapLayout<Datum> {
    /**
     * Lays out the specified root hierarchy.
     * You must call `root.sum` before passing the hierarchy to the treemap layout.
     * You probably also want to call `root.sort` to order the hierarchy before computing the layout.
     *
     * @param root The specified root hierarchy.
     */
    (root: HierarchyNode<Datum>): HierarchyRectangularNode<Datum>;

    /**
     * Returns the current tiling method, which defaults to `d3.treemapSquarify` with the golden ratio.
     */
    tile(): (node: HierarchyRectangularNode<Datum>, x0: number, y0: number, x1: number, y1: number) => void;
    /**
     * Sets the tiling method to the specified function and returns this treemap layout.
     *
     * @param tile The specified tiling function.
     */
    tile(tile: (node: HierarchyRectangularNode<Datum>, x0: number, y0: number, x1: number, y1: number) => void): this;

    /**
     * Returns the current size, which defaults to [1, 1].
     */
    size(): [number, number];
    /**
     * Sets this treemap layout’s size to the specified [width, height] array and returns this treemap layout.
     *
     * @param size The specified two-element size array.
     */
    size(size: [number, number]): this;

    /**
     * Returns the current rounding state, which defaults to false.
     */
    round(): boolean;
    /**
     * Enables or disables rounding according to the given boolean and returns this treemap layout.
     *
     * @param round The specified boolean flag.
     */
    round(round: boolean): this;

    /**
     * Returns the current inner padding function.
     */
    padding(): (node: HierarchyRectangularNode<Datum>) => number;
    /**
     * Sets the inner and outer padding to the specified number and returns this treemap layout.
     *
     * @param padding The specified padding value.
     */
    padding(padding: number): this;
    /**
     * Sets the inner and outer padding to the specified function and returns this treemap layout.
     *
     * @param padding The specified padding function.
     */
    padding(padding: (node: HierarchyRectangularNode<Datum>) => number): this;

    /**
     * Returns the current inner padding function, which defaults to the constant zero.
     */
    paddingInner(): (node: HierarchyRectangularNode<Datum>) => number;
    /**
     * Sets the inner padding to the specified number and returns this treemap layout.
     * The inner padding is used to separate a node’s adjacent children.
     *
     * @param padding The specified inner padding value.
     */
    paddingInner(padding: number): this;
    /**
     * Sets the inner padding to the specified function and returns this treemap layout.
     * The function is invoked for each node with children, being passed the current node.
     * The inner padding is used to separate a node’s adjacent children.
     *
     * @param padding The specified inner padding function.
     */
    paddingInner(padding: (node: HierarchyRectangularNode<Datum>) => number): this;

    /**
     * Returns the current top padding function.
     */
    paddingOuter(): (node: HierarchyRectangularNode<Datum>) => number;
    /**
     * Sets the top, right, bottom and left padding to the specified function and returns this treemap layout.
     *
     * @param padding The specified padding outer value.
     */
    paddingOuter(padding: number): this;
    /**
     * Sets the top, right, bottom and left padding to the specified function and returns this treemap layout.
     *
     * @param padding The specified padding outer function.
     */
    paddingOuter(padding: (node: HierarchyRectangularNode<Datum>) => number): this;

    /**
     * Returns the current top padding function, which defaults to the constant zero.
     */
    paddingTop(): (node: HierarchyRectangularNode<Datum>) => number;
    /**
     * Sets the top padding to the specified number and returns this treemap layout.
     * The top padding is used to separate the top edge of a node from its children.
     *
     * @param padding The specified top padding value.
     */
    paddingTop(padding: number): this;
    /**
     * Sets the top padding to the specified function and returns this treemap layout.
     * The function is invoked for each node with children, being passed the current node.
     * The top padding is used to separate the top edge of a node from its children.
     *
     * @param padding The specified top padding function.
     */
    paddingTop(padding: (node: HierarchyRectangularNode<Datum>) => number): this;

    /**
     * Returns the current right padding function, which defaults to the constant zero.
     */
    paddingRight(): (node: HierarchyRectangularNode<Datum>) => number;
    /**
     * Sets the right padding to the specified number and returns this treemap layout.
     * The right padding is used to separate the right edge of a node from its children.
     *
     * @param padding The specified right padding value.
     */
    paddingRight(padding: number): this;
    /**
     * Sets the right padding to the specified function and returns this treemap layout.
     * The function is invoked for each node with children, being passed the current node.
     * The right padding is used to separate the right edge of a node from its children.
     *
     * @param padding The specified right padding function.
     */
    paddingRight(padding: (node: HierarchyRectangularNode<Datum>) => number): this;

    /**
     * Returns the current bottom padding function, which defaults to the constant zero.
     */
    paddingBottom(): (node: HierarchyRectangularNode<Datum>) => number;
    /**
     * Sets the bottom padding to the specified number and returns this treemap layout.
     * The bottom padding is used to separate the bottom edge of a node from its children.
     *
     * @param padding The specified bottom padding value.
     */
    paddingBottom(padding: number): this;
    /**
     * Sets the bottom padding to the specified function and returns this treemap layout.
     * The function is invoked for each node with children, being passed the current node.
     * The bottom padding is used to separate the bottom edge of a node from its children.
     *
     * @param padding The specified bottom padding function.
     */
    paddingBottom(padding: (node: HierarchyRectangularNode<Datum>) => number): this;

    /**
     * Returns the current left padding function, which defaults to the constant zero.
     */
    paddingLeft(): (node: HierarchyRectangularNode<Datum>) => number;
    /**
     * Sets the left padding to the specified number and returns this treemap layout.
     * The left padding is used to separate the left edge of a node from its children.
     *
     * @param padding The specified left padding value.
     */
    paddingLeft(padding: number): this;
    /**
     * Sets the left padding to the specified function and returns this treemap layout.
     * The function is invoked for each node with children, being passed the current node.
     * The left padding is used to separate the left edge of a node from its children.
     *
     * @param padding The specified left padding function.
     */
    paddingLeft(padding: (node: HierarchyRectangularNode<Datum>) => number): this;
}

/**
 * Creates a new treemap layout with default settings.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function treemap<Datum>(): TreemapLayout<Datum>;

// Tiling functions ------------------------------------------------------

/**
 * Recursively partitions the specified nodes into an approximately-balanced binary tree,
 * choosing horizontal partitioning for wide rectangles and vertical partitioning for tall rectangles.
 */
export function treemapBinary(
    node: HierarchyRectangularNode<any>,
    x0: number,
    y0: number,
    x1: number,
    y1: number,
): void;

/**
 * Divides the rectangular area specified by x0, y0, x1, y1 horizontally according the value of each of the specified node’s children.
 * The children are positioned in order, starting with the left edge (x0) of the given rectangle.
 * If the sum of the children’s values is less than the specified node’s value (i.e., if the specified node has a non-zero internal value),
 * the remaining empty space will be positioned on the right edge (x1) of the given rectangle.
 */
export function treemapDice(node: HierarchyRectangularNode<any>, x0: number, y0: number, x1: number, y1: number): void;

/**
 * Divides the rectangular area specified by x0, y0, x1, y1 vertically according the value of each of the specified node’s children.
 * The children are positioned in order, starting with the top edge (y0) of the given rectangle.
 * If the sum of the children’s values is less than the specified node’s value (i.e., if the specified node has a non-zero internal value),
 * the remaining empty space will be positioned on the bottom edge (y1) of the given rectangle.
 */
export function treemapSlice(node: HierarchyRectangularNode<any>, x0: number, y0: number, x1: number, y1: number): void;

/**
 * If the specified node has odd depth, delegates to treemapSlice; otherwise delegates to treemapDice.
 */
export function treemapSliceDice(
    node: HierarchyRectangularNode<any>,
    x0: number,
    y0: number,
    x1: number,
    y1: number,
): void;

// TODO: Test Factory code
export interface RatioSquarifyTilingFactory {
    (node: HierarchyRectangularNode<any>, x0: number, y0: number, x1: number, y1: number): void;

    /**
     * Specifies the desired aspect ratio of the generated rectangles.
     * Note that the orientation of the generated rectangles (tall or wide) is not implied by the ratio.
     * Furthermore, the rectangles ratio are not guaranteed to have the exact specified aspect ratio.
     * If not specified, the aspect ratio defaults to the golden ratio, φ = (1 + sqrt(5)) / 2, per Kong et al.
     *
     * @param ratio The specified ratio value greater than or equal to one.
     */
    ratio(ratio: number): RatioSquarifyTilingFactory;
}

/**
 * Implements the squarified treemap algorithm by Bruls et al., which seeks to produce rectangles of a given aspect ratio.
 */
export const treemapSquarify: RatioSquarifyTilingFactory;

/**
 * Like `d3.treemapSquarify`, except preserves the topology (node adjacencies) of the previous layout computed by `d3.treemapResquarify`,
 * if there is one and it used the same target aspect ratio. This tiling method is good for animating changes to treemaps because
 * it only changes node sizes and not their relative positions, thus avoiding distracting shuffling and occlusion.
 * The downside of a stable update, however, is a suboptimal layout for subsequent updates: only the first layout uses the Bruls et al. squarified algorithm.
 */
export const treemapResquarify: RatioSquarifyTilingFactory;

// -----------------------------------------------------------------------
// Partition
// -----------------------------------------------------------------------

export interface PartitionLayout<Datum> {
    /**
     * Lays out the specified root hierarchy.
     * You must call `root.sum` before passing the hierarchy to the partition layout.
     * You probably also want to call `root.sort` to order the hierarchy before computing the layout.
     *
     * @param root The specified root hierarchy.
     */
    (root: HierarchyNode<Datum>): HierarchyRectangularNode<Datum>;

    /**
     * Returns the current size, which defaults to [1, 1].
     */
    size(): [number, number];
    /**
     * Sets this partition layout’s size to the specified [width, height] array and returns this partition layout.
     *
     * @param size The specified two-element size array.
     */
    size(size: [number, number]): this;

    /**
     * Returns the current rounding state, which defaults to false.
     */
    round(): boolean;
    /**
     * Enables or disables rounding according to the given boolean and returns this partition layout.
     *
     * @param round The specified boolean flag.
     */
    round(round: boolean): this;

    /**
     * Returns the current padding, which defaults to zero.
     */
    padding(): number;
    /**
     * Sets the padding to the specified number and returns this partition layout.
     * The padding is used to separate a node’s adjacent children.
     *
     * @param padding The specified padding value.
     */
    padding(padding: number): this;
}

/**
 * Creates a new partition layout with the default settings.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function partition<Datum>(): PartitionLayout<Datum>;

// -----------------------------------------------------------------------
// Pack
// -----------------------------------------------------------------------

export interface HierarchyCircularLink<Datum> {
    /**
     * The source of the link.
     */
    source: HierarchyCircularNode<Datum>;

    /**
     * The target of the link.
     */
    target: HierarchyCircularNode<Datum>;
}

export interface HierarchyCircularNode<Datum> extends HierarchyNode<Datum> {
    /**
     * The x-coordinate of the circle’s center.
     */
    x: number;

    /**
     * The y-coordinate of the circle’s center.
     */
    y: number;

    /**
     * The radius of the circle.
     */
    r: number;

    /**
     * Returns an array of links for this node, where each link is an object that defines source and target properties.
     * The source of each link is the parent node, and the target is a child node.
     */
    links(): Array<HierarchyCircularLink<Datum>>;
}

export interface PackLayout<Datum> {
    /**
     * Lays out the specified root hierarchy.
     * You must call `root.sum` before passing the hierarchy to the pack layout.
     * You probably also want to call `root.sort` to order the hierarchy before computing the layout.
     *
     * @param root The specified root hierarchy.
     */
    (root: HierarchyNode<Datum>): HierarchyCircularNode<Datum>;

    /**
     * Returns the current radius accessor, which defaults to null.
     */
    radius(): null | ((node: HierarchyCircularNode<Datum>) => number);
    /**
     * Sets the pack layout’s radius accessor to the specified function and returns this pack layout.
     * If the radius accessor is null, the radius of each leaf circle is derived from the leaf `node.value` (computed by `node.sum`);
     * the radii are then scaled proportionally to fit the layout size.
     * If the radius accessor is not null, the radius of each leaf circle is specified exactly by the function.
     *
     * @param radius The specified radius accessor.
     */
    radius(radius: null | ((node: HierarchyCircularNode<Datum>) => number)): this;

    /**
     * Returns the current size, which defaults to [1, 1].
     */
    size(): [number, number];
    /**
     * Sets this pack layout’s size to the specified [width, height] array and returns this pack layout.
     *
     * @param size The specified two-element size array.
     */
    size(size: [number, number]): this;

    /**
     * Returns the current padding accessor, which defaults to the constant zero.
     */
    padding(): (node: HierarchyCircularNode<Datum>) => number;
    /**
     * Sets this pack layout’s padding accessor to the specified number and returns this pack layout.
     * Returns the current padding accessor, which defaults to the constant zero.
     *
     * When siblings are packed, tangent siblings will be separated by approximately the specified padding;
     * the enclosing parent circle will also be separated from its children by approximately the specified padding.
     * If an explicit radius is not specified, the padding is approximate because a two-pass algorithm
     * is needed to fit within the layout size: the circles are first packed without padding;
     * a scaling factor is computed and applied to the specified padding; and lastly the circles are re-packed with padding.
     *
     * @param padding The specified padding value.
     */
    padding(padding: number): this;
    /**
     * Sets this pack layout’s padding accessor to the specified function and returns this pack layout.
     * Returns the current padding accessor, which defaults to the constant zero.
     *
     * When siblings are packed, tangent siblings will be separated by approximately the specified padding;
     * the enclosing parent circle will also be separated from its children by approximately the specified padding.
     * If an explicit radius is not specified, the padding is approximate because a two-pass algorithm
     * is needed to fit within the layout size: the circles are first packed without padding;
     * a scaling factor is computed and applied to the specified padding; and lastly the circles are re-packed with padding.
     *
     * @param padding The specified padding function.
     */
    padding(padding: (node: HierarchyCircularNode<Datum>) => number): this;
}

/**
 * Creates a new pack layout with the default settings.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function pack<Datum>(): PackLayout<Datum>;

// -----------------------------------------------------------------------
// Pack Siblings and Enclosure
// -----------------------------------------------------------------------

export interface PackRadius {
    /**
     * The radius of the circle.
     */
    r: number;

    /**
     * The x-coordinate of the circle’s center.
     */
    x?: number | undefined;

    /**
     * The y-coordinate of the circle’s center.
     */
    y?: number | undefined;
}

export interface PackCircle {
    /**
     * The radius of the circle.
     */
    r: number;

    /**
     * The x-coordinate of the circle’s center.
     */
    x: number;

    /**
     * The y-coordinate of the circle’s center.
     */
    y: number;
}

// TODO: Since packSiblings manipulates the circles array in place, technically the x and y properties
// are optional on invocation, but will be created after execution for each entry.

/**
 * Packs the specified array of circles, each of which must have a `circle.r` property specifying the circle’s radius.
 * The circles are positioned according to the front-chain packing algorithm by Wang et al.
 *
 * @param circles The specified array of circles to pack.
 */
export function packSiblings<Datum extends PackRadius>(circles: Datum[]): Array<Datum & PackCircle>;

/**
 * Computes the smallest circle that encloses the specified array of circles, each of which must have
 * a `circle.r` property specifying the circle’s radius, and `circle.x` and `circle.y` properties specifying the circle’s center.
 * The enclosing circle is computed using the Matoušek-Sharir-Welzl algorithm. (See also Apollonius’ Problem.)
 *
 * @param circles The specified array of circles to pack.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function packEnclose<Datum extends PackCircle>(circles: Datum[]): PackCircle;
