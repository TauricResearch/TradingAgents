// Last module patch version validated against: 3.0.1

// ---------------------------------------------------------------------
// Chord
// ---------------------------------------------------------------------

/**
 * A chord subgroup serving as source or target of a chord between two nodes i an j (where i may be equal to j).
 */
export interface ChordSubgroup {
    /**
     * Start angle of the chord subgroup in radians
     */
    startAngle: number;

    /***
     * End angle of the chord subgroup in radians
     */
    endAngle: number;

    /**
     * The flow value in matrix[i][j] from node i to node j
     */
    value: number;

    /**
     * The node index i
     */
    index: number;
}

/**
 * A chord represents the combined bidirectional flow between two nodes i and j (where i may be equal to j)
 */
export interface Chord {
    /**
     * Chord subgroup constituting the source of Chord
     */
    source: ChordSubgroup;
    /**
     * Chord subgroup constituting the Target of Chord
     */
    target: ChordSubgroup;
}

/**
 * A chord group for a given node i representing the combined outflow for node i,
 * corresponding to the elements matrix[i][0 … n - 1].
 */
export interface ChordGroup {
    /**
     * The start angle of the chord group in radians
     */
    startAngle: number;

    /**
     * The end angle of the chord group in radians
     */
    endAngle: number;

    /**
     * The total outgoing flow value for node i
     */
    value: number;

    /**
     * The node index i
     */
    index: number;
}

/**
 * An array of chords, where each chord represents the combined bidirectional flow between two nodes i and j (where i may be equal to j).
 * The chords are based on a (n x n) matrix of flows between nodes.
 *
 * The chords are typically passed to d3.ribbon to display the network relationships.
 * The returned array includes only chord objects for which the value matrix[i][j] or matrix[j][i] is non-zero.
 * Furthermore, the returned array only contains unique chords: a given chord ij represents the bidirectional flow from i to j and from j to i,
 * and does not contain a duplicate chord ji; i and j are chosen such that the chord’s source always represents the larger of matrix[i][j] and matrix[j][i].
 * In other words, chord.source.index equals chord.target.subindex, chord.source.subindex equals chord.target.index,
 * chord.source.value is greater than or equal to chord.target.value, and chord.source.value is always greater than zero.
 */
export interface Chords extends Array<Chord> {
    /**
     * An array of length n, where each group represents the combined outflow for node i,
     * corresponding to the elements matrix[i][0 … n - 1]
     */
    groups: ChordGroup[];
}

/**
 * A D3 chord diagram Layout to visualize relationships or network flow with an aesthetically-pleasing circular layout.
 *
 * The relationships are represented as a square matrix of size n×n, where the matrix represents the directed flow amongst a network (a complete digraph) of n nodes.
 */
export interface ChordLayout {
    /**
     * Computes the chord layout for the specified square matrix of size n×n, where the matrix represents the directed flow amongst a network (a complete digraph) of n nodes.
     *
     * @param matrix An (n x n) matrix representing the directed flow amongst a network (a complete digraph) of n nodes.The given matrix must be an array of length n,
     * where each element matrix[i] is an array of n numbers, where each matrix[i][j] represents the flow from the ith node in the network to the jth node.
     * Each number matrix[i][j] must be nonnegative, though it can be zero if there is no flow from node i to node j.
     */
    (matrix: number[][]): Chords;

    /**
     * Returns the current pad angle in radians, which defaults to zero.
     */
    padAngle(): number;
    /**
     * Sets the pad angle between adjacent groups to the specified number in radians and returns this chord layout.
     *
     * The default is zero.
     *
     * @param angle Pad angle between adjacent groups in radians.
     */
    padAngle(angle: number): this;

    /**
     * Returns the current group comparator, which defaults to null.
     */
    sortGroups(): ((a: number, b: number) => number) | null;
    /**
     * Sets the group comparator to the specified function or null and returns this chord layout.
     * If the group comparator is non-null, it is used to sort the groups by their total outflow.
     * See also d3.ascending and d3.descending.
     */
    sortGroups(compare: null | ((a: number, b: number) => number)): this;

    /**
     * Returns the current subgroup comparator, which defaults to null.
     */
    sortSubgroups(): ((a: number, b: number) => number) | null;
    /**
     * Sets the subgroup comparator to the specified function or null and returns this chord layout.
     * If the subgroup comparator is non-null, it is used to sort the subgroups corresponding to matrix[i][0 … n - 1] for a given group i by their total outflow.
     * See also d3.ascending and d3.descending.
     */
    sortSubgroups(compare: null | ((a: number, b: number) => number)): this;

    /**
     * Returns the current chord comparator, which defaults to null.
     */
    sortChords(): ((a: number, b: number) => number) | null;
    /**
     * Sets the chord comparator to the specified function or null and returns this chord layout.
     * If the chord comparator is non-null, it is used to sort the chords by their combined flow; this only affects the z-order of the chords.
     * See also d3.ascending and d3.descending.
     */
    sortChords(compare: null | ((a: number, b: number) => number)): this;
}

/**
 * Constructs a new chord diagram layout with the default settings.
 */
export function chord(): ChordLayout;

/**
 * A chord layout for directional flows. The chord from i to j is generated from the value in matrix[i][j] only.
 */
export function chordDirected(): ChordLayout;

/**
 * A transposed chord layout. Useful to highlight outgoing (rather than incoming) flows.
 */
export function chordTranspose(): ChordLayout;

// ---------------------------------------------------------------------
// Ribbon
// ---------------------------------------------------------------------

/**
 * A minimal interface to support the default accessors used by RibbonGenerator for properties of
 * source and target objects of a Ribbon.
 *
 * (Corresponds to ChordSubgroup)
 */
export interface RibbonSubgroup {
    /**
     * Start angle of the ribbon subgroup in radians
     */
    startAngle: number;
    /**
     * End angle of the ribbon subgroup in radians
     */
    endAngle: number;
    /**
     * Radius of the ribbon subgroup
     */
    radius: number;
}

/**
 * A minimal interface to support the default source and target accessors used by RibbonGenerator.
 * (Corresponds to Chord)
 */
export interface Ribbon {
    /**
     * Ribbon subgroup constituting the source of the Ribbon
     */
    source: RibbonSubgroup;
    /**
     * Ribbon subgroup constituting the target of the Ribbon
     */
    target: RibbonSubgroup;
}

/**
 * A ribbon generator to support rendering of chords in a chord diagram.
 *
 * The first generic corresponds to the type of the "this" context within which the ribbon generator and its accessor functions will be invoked.
 *
 * The second generic corresponds to the datum type representing a chord for which the ribbon is to be generated. The default type is Ribbon.
 *
 * The third generic corresponds to the datum type of the chord subgroup, i.e. source or target of the cord. The default type is RibbonSubgroup.
 */
export interface RibbonGenerator<This, RibbonDatum, RibbonSubgroupDatum> {
    /**
     * Generates a ribbon for the given arguments.
     *
     * IMPORTANT: If the ribbon generator has been configured with a rendering context,
     * then the ribbon is rendered to this context as a sequence of path method calls and this function returns void.
     *
     * The "this" context within which this function is invoked, will be the context within which the accessor methods of the generator are invoked.
     * All arguments passed into this function, will be passed to the accessor functions of the generator.
     *
     * @param d The datum representing the chord for which the ribbon is to be generated.
     */
    (this: This, d: RibbonDatum, ...args: any[]): void;
    /**
     * Generates a ribbon for the given arguments.
     *
     * IMPORTANT: If the rendering context of the ribbon generator is null,
     * then the ribbon is returned as a path data string.
     *
     * The "this" context within which this function is invoked, will be the context within which the accessor methods of the generator are invoked.
     * All arguments passed into this function, will be passed to the accessor functions of the generator.
     *
     * @param d The datum representing the chord for which the ribbon is to be generated.
     */
    (this: This, d: RibbonDatum, ...args: any[]): string | null;

    /**
     * Returns the current source accessor, which defaults to a function returning the "source" property of the first argument passed into the accessor.
     */
    source(): (this: This, d: RibbonDatum, ...args: any[]) => RibbonSubgroupDatum;
    /**
     * Sets the source accessor to the specified function and returns this ribbon generator.
     *
     * @param source An accessor function returning the source datum of the chord. The accessor function is invoked in the same "this" context as the generator was invoked in and
     * receives the same arguments that were passed into the ribbon generator.
     */
    source(source: (this: This, d: RibbonDatum, ...args: any[]) => RibbonSubgroupDatum): this;

    /**
     * Returns the current target accessor, which defaults to a function returning the "target" property of the first argument passed into the accessor.
     */
    target(): (this: This, d: RibbonDatum, ...args: any[]) => RibbonSubgroupDatum;
    /**
     * Sets the target accessor to the specified function and returns this ribbon generator.
     *
     * @param target An accessor function returning the target datum of the chord. The accessor function is invoked in the same "this" context as the generator was invoked in and
     * receives the same arguments that were passed into the ribbon generator.
     */
    target(target: (this: This, d: RibbonDatum, ...args: any[]) => RibbonSubgroupDatum): this;

    /**
     * Returns the current radius accessor, which defaults to a function returning the "radius" property (assumed to be a number) of the source or
     * target object returned by the source or target accessor, respectively.
     */
    radius(): (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number;
    /**
     * Sets the radius to a fixed number and returns this ribbon generator.
     *
     * @param radius A fixed numeric value for the radius.
     */
    radius(radius: number): this;
    /**
     * Sets the radius accessor to the specified function and returns this ribbon generator.
     *
     * @param radius An accessor function which is invoked for the source and target of the chord. The accessor function is invoked in the same "this" context as the generator was invoked in and
     * receives as the first argument the source or target object returned by the respective source or target accessor function of the generator.
     * It is also passed any additional arguments that were passed into the generator, with the exception of the first element representing the chord datum itself.
     * The function returns the radius value.
     */
    radius(radius: (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number): this;

    /**
     * Returns the current source radius accessor, which defaults to a function returning the "radius" property (assumed to be a number) of the source or
     * target object returned by the source or target accessor, respectively.
     */
    sourceRadius(): (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number;
    /**
     * Sets the source radius to a fixed number and returns this ribbon generator.
     *
     * @param radius A fixed numeric value for the source radius.
     */
    sourceRadius(radius: number): this;
    /**
     * Sets the source radius accessor to the specified function and returns this ribbon generator.
     *
     * @param radius An accessor function which is invoked for the source and target of the chord. The accessor function is invoked in the same "this" context as the generator was invoked in and
     * receives as the first argument the source or target object returned by the respective source or target accessor function of the generator.
     * It is also passed any additional arguments that were passed into the generator, with the exception of the first element representing the chord datum itself.
     * The function returns the source radius value.
     */
    sourceRadius(radius: (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number): this;

    /**
     * Returns the current target radius accessor, which defaults to a function returning the "radius" property (assumed to be a number) of the source or
     * target object returned by the source or target accessor, respectively.
     */
    targetRadius(): (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number;
    /**
     * Sets the target radius to a fixed number and returns this ribbon generator.
     *
     * @param radius A fixed numeric value for the target radius.
     */
    targetRadius(radius: number): this;
    /**
     * Sets the target radius accessor to the specified function and returns this ribbon generator.
     *
     * @param radius An accessor function which is invoked for the source and target of the chord. The accessor function is invoked in the same "this" context as the generator was invoked in and
     * receives as the first argument the source or target object returned by the respective source or target accessor function of the generator.
     * It is also passed any additional arguments that were passed into the generator, with the exception of the first element representing the chord datum itself.
     * The function returns the target radius value.
     */
    targetRadius(radius: (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number): this;

    /**
     * Returns the current start angle accessor, which defaults to a function returning the "startAngle" property (assumed to be a number in radians) of the source or
     * target object returned by the source or target accessor, respectively.
     */
    startAngle(): (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number;
    /**
     * Sets the start angle to a fixed number in radians and returns this ribbon generator.
     *
     * @param angle A fixed numeric value for the start angle in radians.
     */
    startAngle(angle: number): this;
    /**
     * Sets the start angle accessor to the specified function and returns this ribbon generator.
     *
     * @param angle An accessor function which is invoked for the source and target of the chord. The accessor function is invoked in the same "this" context as the generator was invoked in and
     * receives as the first argument the source or target object returned by the respective source or target accessor function of the generator.
     * It is also passed any additional arguments that were passed into the generator, with the exception of the first element representing the chord datum itself.
     * The function returns the start angle in radians.
     */
    startAngle(angle: (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number): this;

    /**
     * Returns the current end angle accessor, which defaults to a function returning the "endAngle" property (assumed to be a number in radians) of the source or
     * target object returned by the source or target accessor, respectively.
     */
    endAngle(): (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number;
    /**
     * Sets the end angle to a fixed number in radians and returns this ribbon generator.
     *
     * @param angle A fixed numeric value for the end angle in radians.
     */
    endAngle(angle: number): this;
    /**
     * Sets the end angle accessor to the specified function and returns this ribbon generator.
     *
     * @param angle An accessor function which is invoked for the source and target of the chord. The accessor function is invoked in the same "this" context as the generator was invoked in and
     * receives as the first argument the source or target object returned by the respective source or target accessor function of the generator.
     * It is also passed any additional arguments that were passed into the generator, with the exception of the first element representing the chord datum itself.
     * The function returns the end angle in radians.
     */
    endAngle(angle: (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number): this;

    /**
     * Returns the current pad angle accessor, which defaults to a function returning 0.
     */
    padAngle(): (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number;
    /**
     * Sets the pad angle to a fixed number in radians and returns this ribbon generator.
     *
     * @param angle A fixed numeric value for the pad angle in radians.
     */
    padAngle(angle: number): this;
    /**
     * Sets the pad angle accessor to the specified function and returns this ribbon generator.
     *
     * @param angle An accessor function which is invoked for the source and target of the chord. The accessor function is invoked in the same "this" context as the generator was invoked in and
     * receives as the first argument the source or target object returned by the respective source or target accessor function of the generator.
     * It is also passed any additional arguments that were passed into the generator, with the exception of the first element representing the chord datum itself.
     * The function returns the pad angle in radians.
     */
    padAngle(angle: (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number): this;

    /**
     * Returns the current rendering context, which defaults to null.
     */
    context(): CanvasRenderingContext2D | null;
    /**
     * Sets the context and returns this ribbon generator.
     * If the context is not null, then the generated ribbon is rendered to this context as a sequence of path method calls.
     * Otherwise, a path data string representing the generated ribbon is returned.
     * See also d3-path.
     */
    context(context: CanvasRenderingContext2D | null): this;
}

export interface RibbonArrowGenerator<This, RibbonDatum, RibbonSubgroupDatum>
    extends RibbonGenerator<This, RibbonDatum, RibbonSubgroupDatum>
{
    headRadius(): (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number;

    headRadius(radius: number): this;

    headRadius(radius: (this: This, d: RibbonSubgroupDatum, ...args: any[]) => number): this;
}

/**
 * Creates a new ribbon generator with the default settings.
 */
export function ribbon(): RibbonGenerator<any, Ribbon, RibbonSubgroup>;
/**
 * Creates a new ribbon generator with the default settings.
 *
 * Accessor functions must be configured for the ribbon generator, should the datum types differ from the defaults.
 *
 * The first generic corresponds to the datum type representing a chord for which the ribbon is to be generated. The default type is Chord.
 *
 * The second generic corresponds to the datum type of the chord subgroup, i.e. source or target of the cord. The default type is ChordSubgroup.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function ribbon<Datum, SubgroupDatum>(): RibbonGenerator<any, Datum, SubgroupDatum>;
/**
 * Creates a new ribbon generator with the default settings.
 *
 * Accessor functions must be configured for the ribbon generator, should the datum types differ from the defaults.
 *
 * The first generic corresponds to the type of the "this" context within which the ribbon generator and its accessor functions will be invoked.
 *
 * The second generic corresponds to the datum type representing a chord for which the ribbon is to be generated. The default type is Chord.
 *
 * The third generic corresponds to the datum type of the chord subgroup, i.e. source or target of the cord. The default type is ChordSubgroup.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function ribbon<This, Datum, SubgroupDatum>(): RibbonGenerator<This, Datum, SubgroupDatum>;

/**
 * Creates a new arrow ribbon generator with the default settings.
 */
export function ribbonArrow(): RibbonArrowGenerator<any, Ribbon, RibbonSubgroup>;
/**
 * Creates a new arrow ribbon generator with the default settings.
 *
 * Accessor functions must be configured for the ribbon generator, should the datum types differ from the defaults.
 *
 * The first generic corresponds to the datum type representing a chord for which the ribbon is to be generated. The default type is Chord.
 *
 * The second generic corresponds to the datum type of the chord subgroup, i.e. source or target of the cord. The default type is ChordSubgroup.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function ribbonArrow<Datum, SubgroupDatum>(): RibbonArrowGenerator<any, Datum, SubgroupDatum>;
/**
 * Creates a new arrow ribbon generator with the default settings.
 *
 * Accessor functions must be configured for the ribbon generator, should the datum types differ from the defaults.
 *
 * The first generic corresponds to the type of the "this" context within which the ribbon generator and its accessor functions will be invoked.
 *
 * The second generic corresponds to the datum type representing a chord for which the ribbon is to be generated. The default type is Chord.
 *
 * The third generic corresponds to the datum type of the chord subgroup, i.e. source or target of the cord. The default type is ChordSubgroup.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function ribbonArrow<This, Datum, SubgroupDatum>(): RibbonArrowGenerator<This, Datum, SubgroupDatum>;
