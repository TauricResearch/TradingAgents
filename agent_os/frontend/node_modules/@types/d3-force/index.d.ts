// Last module patch version validated against: 3.0.0

// -----------------------------------------------------------------------
// Force Simulation
// -----------------------------------------------------------------------

/**
 * The base data structure for the datum of a Simulation Node.
 * The optional properties contained in this data structure are internally assigned
 * by the Simulation upon (re-)initialization.
 *
 * When defining a data type to use for node data, it should be an extension of this interface
 * and respect the already "earmarked" properties used by the simulation.
 *
 * IMPORTANT: Prior to initialization, the following properties are optional: index, x, y, vx, and vy.
 * After initialization they will be defined. The optional properties fx and fy are ONLY defined,
 * if the node's position has been fixed.
 */
export interface SimulationNodeDatum {
    /**
     * Node’s zero-based index into nodes array. This property is set during the initialization process of a simulation.
     */
    index?: number | undefined;
    /**
     * Node’s current x-position
     */
    x?: number | undefined;
    /**
     * Node’s current y-position
     */
    y?: number | undefined;
    /**
     * Node’s current x-velocity
     */
    vx?: number | undefined;
    /**
     * Node’s current y-velocity
     */
    vy?: number | undefined;
    /**
     * Node’s fixed x-position (if position was fixed)
     */
    fx?: number | null | undefined;
    /**
     * Node’s fixed y-position (if position was fixed)
     */
    fy?: number | null | undefined;
}

/**
 * The base data structure for the datum of a Simulation Link, as used by ForceLink.
 * The optional properties contained in this data structure are internally assigned
 * by when initializing with ForceLink.links(...)
 *
 * IMPORTANT: The source and target properties may be internally mutated in type during the
 * ForceLink initialization process (possibly being changed from a node index in the nodes array,
 * or a node id string to the simulation node object which was mapped in using the current
 * ForceLink.id(...) accessor function.)
 */
export interface SimulationLinkDatum<NodeDatum extends SimulationNodeDatum> {
    /**
     * Link’s source node.
     * For convenience, a link’s source and target properties may be initialized using numeric or string identifiers rather than object references; see link.id.
     * When the link force is initialized (or re-initialized, as when the nodes or links change), any link.source or link.target property which is not an object
     * is replaced by an object reference to the corresponding node with the given identifier.
     * After initialization, the source property represents the source node object.
     */
    source: NodeDatum | string | number;
    /**
     * Link’s source link
     * For convenience, a link’s source and target properties may be initialized using numeric or string identifiers rather than object references; see link.id.
     * When the link force is initialized (or re-initialized, as when the nodes or links change), any link.source or link.target property which is not an object
     * is replaced by an object reference to the corresponding node with the given identifier.
     * After initialization, the target property represents the target node object.
     */
    target: NodeDatum | string | number;
    /**
     * The zero-based index into the links array. Internally generated when calling ForceLink.links(...)
     */
    index?: number | undefined;
}

/**
 * A Force Simulation
 *
 * The first generic refers to the type of the datum associated with a node in the simulation.
 * The second generic refers to the type of the datum associated with a link in the simulation, if applicable.
 */
export interface Simulation<
    NodeDatum extends SimulationNodeDatum,
    LinkDatum extends SimulationLinkDatum<NodeDatum> | undefined,
> {
    /**
     * Restart the simulation’s internal timer and return the simulation.
     * In conjunction with simulation.alphaTarget or simulation.alpha, this method can be used to “reheat” the simulation during interaction,
     * such as when dragging a node, or to resume the simulation after temporarily pausing it with simulation.stop.
     */
    restart(): this;

    /**
     * Stop the simulation’s internal timer, if it is running, and return the simulation. If the timer is already stopped, this method does nothing.
     * This method is useful for running the simulation manually; see simulation.tick.
     */
    stop(): this;

    /**
     * Manually steps the simulation by the specified number of *iterations*, and returns the simulation. If *iterations* is not specified, it defaults to 1 (single step).
     *
     * For each iteration, it increments the current alpha by (alphaTarget - alpha) × alphaDecay; then invokes each registered force, passing the new alpha;
     * then decrements each node’s velocity by velocity × velocityDecay; lastly increments each node’s position by velocity.
     *
     * This method does not dispatch events; events are only dispatched by the internal timer when the simulation is started automatically upon
     * creation or by calling simulation.restart. The natural number of ticks when the simulation is started is
     * ⌈log(alphaMin) / log(1 - alphaDecay)⌉; by default, this is 300.
     */
    tick(iterations?: number): this;

    /**
     * Returns the simulation’s array of nodes as specified to the constructor.
     */
    nodes(): NodeDatum[];
    /**
     * Set the simulation’s nodes to the specified array of objects, initialize their positions and velocities if necessary,
     * and then re-initialize any bound forces; Returns the simulation.
     *
     * Each node must be an object. The following properties are assigned by the simulation:
     * - index (the node’s zero-based index into nodes)
     * - x (the node’s current x-position)
     * - y (the node’s current y-position)
     * - vx (the node’s current x-velocity)
     * - vy (the node’s current y-velocity)
     *
     * The position [x,y] and velocity [vx,vy] may be subsequently modified by forces and by the simulation.
     * If either vx or vy is NaN, the velocity is initialized to [0,0]. If either x or y is NaN, the position is initialized in a phyllotaxis arrangement,
     * so chosen to ensure a deterministic, uniform distribution.
     *
     * To fix a node in a given position, you may specify two additional properties:
     * - fx (the node’s fixed x-position)
     * - fy (the node’s fixed y-position)
     *
     * At the end of each tick, after the application of any forces, a node with a defined node.fx has node.x reset to this value and node.vx set to zero;
     * likewise, a node with a defined node.fy has node.y reset to this value and node.vy set to zero.
     * To unfix a node that was previously fixed, set node.fx and node.fy to null, or delete these properties.
     *
     * If the specified array of nodes is modified, such as when nodes are added to or removed from the simulation,
     * this method must be called again with the new (or changed) array to notify the simulation and bound forces of the change;
     * the simulation does not make a defensive copy of the specified array.
     */
    nodes(nodesData: NodeDatum[]): this;

    /**
     * Return the current alpha of the simulation, which defaults to 1.
     *
     * alpha is roughly analogous to temperature in simulated annealing.
     * It decreases over time as the simulation “cools down”.
     * When alpha reaches alphaMin, the simulation stops; see simulation.restart.
     */
    alpha(): number;
    /**
     * Set the current alpha to the specified number in the range [0,1] and return this simulation.
     * The default is 1.
     *
     * alpha is roughly analogous to temperature in simulated annealing.
     * It decreases over time as the simulation “cools down”.
     * When alpha reaches alphaMin, the simulation stops; see simulation.restart.
     *
     * @param alpha Current alpha of simulation.
     */
    alpha(alpha: number): this;

    /**
     * Return the current minimum alpha value, which defaults to 0.001.
     */
    alphaMin(): number;
    /**
     * Set the minimum alpha to the specified number in the range [0,1] and return this simulation.
     * The default is 0.001. The simulation’s internal timer stops when the current alpha is less than the minimum alpha.
     * The default alpha decay rate of ~0.0228 corresponds to 300 iterations.
     *
     * @param min Minimum alpha of simulation.
     */
    alphaMin(min: number): this;

    /**
     * Return the current alpha decay rate, which defaults to 0.0228… = 1 - pow(0.001, 1 / 300) where 0.001 is the default minimum alpha.
     */
    alphaDecay(): number;
    /**
     * Set the alpha decay rate to the specified number in the range [0,1] and return this simulation.
     * The default is 0.0228… = 1 - pow(0.001, 1 / 300) where 0.001 is the default minimum alpha.
     *
     * The alpha decay rate determines how quickly the current alpha interpolates towards the desired target alpha;
     * since the default target alpha is zero, by default this controls how quickly the simulation cools.
     * Higher decay rates cause the simulation to stabilize more quickly, but risk getting stuck in a local minimum;
     * lower values cause the simulation to take longer to run, but typically converge on a better layout.
     * To have the simulation run forever at the current alpha, set the decay rate to zero;
     * alternatively, set a target alpha greater than the minimum alpha.
     *
     * @param decay Alpha decay rate.
     */
    alphaDecay(decay: number): this;

    /**
     * Returns the current target alpha value, which defaults to 0.
     */
    alphaTarget(): number;
    /**
     * Set the current target alpha to the specified number in the range [0,1] and return this simulation.
     * The default is 0.
     *
     * @param target Alpha target value.
     */
    alphaTarget(target: number): this;

    /**
     * Return the current target alpha value, which defaults to 0.4.
     */
    velocityDecay(): number;
    /**
     * Set the velocity decay factor to the specified number in the range [0,1] and return this simulation.
     * The default is 0.4.
     *
     * The decay factor is akin to atmospheric friction; after the application of any forces during a tick,
     * each node’s velocity is multiplied by 1 - decay. As with lowering the alpha decay rate,
     * less velocity decay may converge on a better solution, but risks numerical instabilities and oscillation.
     *
     * @param decay Velocity Decay.
     */
    velocityDecay(decay: number): this;

    /**
     * Return the force with the specified name, or undefined if there is no such force.
     * (By default, new simulations have no forces.)
     *
     * Given that it is in general not known, what type of force has been registered under
     * a specified name, use the generic to cast the result to the appropriate type, if known.
     *
     * @param name Name of the registered force.
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    force<F extends Force<NodeDatum, LinkDatum>>(name: string): F | undefined;
    /**
     * If force is specified, assigns the force for the specified name and returns this simulation.
     * To remove the force with the given name, pass null as the force.
     */
    force(name: string, force: null | Force<NodeDatum, LinkDatum>): this;

    /**
     * Return the node closest to the position [x,y] with the given search radius.
     * If radius is not specified, it defaults to infinity.
     * If there is no node within the search area, returns undefined.
     *
     * @param x x-coordinate
     * @param y y-coordinate
     * @param radius Optional search radius. Defaults to infinity.
     */
    find(x: number, y: number, radius?: number): NodeDatum | undefined;

    /**
     * Returns this simulation’s current random source which defaults to a fixed-seed linear congruential generator.
     * See also random.source.
     */
    randomSource(): () => number;
    /**
     * Sets the function used to generate random numbers; this should be a function that returns a number between 0 (inclusive) and 1 (exclusive).
     *
     * @param source The function used to generate random numbers.
     */
    randomSource(source: () => number): this;

    /**
     * Return the first currently-assigned listener matching the specified typenames, if any.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace. Each typename is a type,
     * optionally followed by a period (.) and a name, such as "tick.foo" and "tick.bar"; the name allows multiple listeners to be registered for the same type.
     * The type must be one of the following: "tick" (after each tick of the simulation’s internal timer) or
     * "end" (after the simulation’s timer stops when alpha < alphaMin).
     */
    on(typenames: "tick" | "end" | string): ((this: Simulation<NodeDatum, LinkDatum>) => void) | undefined;
    /**
     * Sets the event listener for the specified typenames and returns this simulation.
     * If an event listener was already registered for the same type and name, the existing listener is removed before the new listener is added.
     * If listener is null, removes the current event listeners for the specified typenames, if any.
     * When a specified event is dispatched, each listener will be invoked with the this context as the simulation.
     */
    on(typenames: "tick" | "end" | string, listener: null | ((this: this) => void)): this;
}

/**
 * Create a new simulation with the specified array of nodes and no forces.
 * If nodes is not specified, it defaults to the empty array.
 * The simulator starts automatically; use simulation.on to listen for tick events as the simulation runs.
 * If you wish to run the simulation manually instead, call simulation.stop, and then call simulation.tick as desired.
 *
 * Use this signature, when creating a simulation WITHOUT link force(s).
 *
 * The generic refers to the type of the data for a node.
 *
 * @param nodesData Optional array of nodes data, defaults to empty array.
 */
export function forceSimulation<NodeDatum extends SimulationNodeDatum>(
    nodesData?: NodeDatum[],
): Simulation<NodeDatum, undefined>;
/**
 * Create a new simulation with the specified array of nodes and no forces.
 * If nodes is not specified, it defaults to the empty array.
 * The simulator starts automatically; use simulation.on to listen for tick events as the simulation runs.
 * If you wish to run the simulation manually instead, call simulation.stop, and then call simulation.tick as desired.
 *
 * Use this signature, when creating a simulation WITH link force(s).
 *
 * The first generic refers to the type of data for a node.
 * The second generic refers to the type of data for a link.
 *
 * @param nodesData Optional array of nodes data, defaults to empty array.
 */
export function forceSimulation<
    NodeDatum extends SimulationNodeDatum,
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    LinkDatum extends SimulationLinkDatum<NodeDatum>,
>(nodesData?: NodeDatum[]): Simulation<NodeDatum, LinkDatum>;

// ----------------------------------------------------------------------
// Forces
// ----------------------------------------------------------------------

/**
 * A force is simply a function that modifies nodes’ positions or velocities; in this context, a force can apply a classical physical force such as electrical charge or gravity,
 * or it can resolve a geometric constraint, such as keeping nodes within a bounding box or keeping linked nodes a fixed distance apart.
 *
 * Forces typically read the node’s current position [x,y] and then add to (or subtract from) the node’s velocity [vx,vy].
 * However, forces may also “peek ahead” to the anticipated next position of the node, [x + vx,y + vy]; this is necessary for resolving geometric constraints through iterative relaxation.
 * Forces may also modify the position directly, which is sometimes useful to avoid adding energy to the simulation, such as when recentering the simulation in the viewport.
 *
 * Forces may optionally implement force.initialize to receive the simulation’s array of nodes.
 */
export interface Force<
    NodeDatum extends SimulationNodeDatum,
    LinkDatum extends SimulationLinkDatum<NodeDatum> | undefined,
> {
    /**
     * Apply this force, optionally observing the specified alpha.
     * Typically, the force is applied to the array of nodes previously passed to force.initialize,
     * however, some forces may apply to a subset of nodes, or behave differently.
     * For example, d3.forceLink applies to the source and target of each link.
     */
    (alpha: number): void;
    /**
     * Supplies the array of nodes and random source to this force. This method is called when a force is bound to a simulation via simulation.force
     * and when the simulation’s nodes change via simulation.nodes.
     *
     * A force may perform necessary work during initialization, such as evaluating per-node parameters, to avoid repeatedly performing work during each application of the force.
     */
    initialize?(nodes: NodeDatum[], random: () => number): void;
}

// Centering ------------------------------------------------------------

/**
 * The centering force translates nodes uniformly so that the mean position of all nodes
 * (the center of mass if all nodes have equal weight) is at the given position [x,y].
 * This force modifies the positions of nodes on each application; it does not modify velocities,
 * as doing so would typically cause the nodes to overshoot and oscillate around the desired center.
 * This force helps keeps nodes in the center of the viewport, and unlike the positioning force,
 * it does not distort their relative positions.
 *
 * The generic refers to the type of data for a node.
 */
export interface ForceCenter<NodeDatum extends SimulationNodeDatum> extends Force<NodeDatum, any> {
    /**
     * Supplies the array of nodes and random source to this force. This method is called when a force is bound to a simulation via simulation.force
     * and when the simulation’s nodes change via simulation.nodes.
     *
     * A force may perform necessary work during initialization, such as evaluating per-node parameters, to avoid repeatedly performing work during each application of the force.
     */
    initialize(nodes: NodeDatum[], random: () => number): void;

    /**
     * Return the current x-coordinate of the centering position, which defaults to zero.
     */
    x(): number;
    /**
     * Set the x-coordinate of the centering position.
     *
     * @param x x-coordinate.
     */
    x(x: number): this;

    /**
     * Return the current y-coordinate of the centering position, which defaults to zero.
     */
    y(): number;
    /**
     * Set the y-coordinate of the centering position.
     *
     * @param y y-coordinate.
     */
    y(y: number): this;

    /**
     * Returns the force’s current strength, which defaults to 1.
     */
    strength(): number;

    /**
     * Sets the centering force’s strength.
     * A reduced strength of e.g. 0.05 softens the movements on interactive graphs in which new nodes enter or exit the graph.
     * @param strength The centering force's strength.
     */
    strength(strength: number): this;
}

/**
 * Create a new centering force with the specified x- and y- coordinates.
 * If x and y are not specified, they default to [0,0].
 *
 * The centering force translates nodes uniformly so that the mean position of all nodes
 * (the center of mass if all nodes have equal weight) is at the given position [x,y].
 * This force modifies the positions of nodes on each application; it does not modify velocities,
 * as doing so would typically cause the nodes to overshoot and oscillate around the desired center.
 * This force helps keeps nodes in the center of the viewport, and unlike the positioning force,
 * it does not distort their relative positions.
 *
 * The generic refers to the type of data for a node.
 *
 * @param x An optional x-coordinate for the centering position, defaults to 0.
 * @param y An optional y-coordinate for the centering position, defaults to 0.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function forceCenter<NodeDatum extends SimulationNodeDatum>(x?: number, y?: number): ForceCenter<NodeDatum>;

// Collision ------------------------------------------------------------

/**
 * The collision force treats nodes as circles with a given radius, rather than points, and prevents nodes from overlapping.
 * More formally, two nodes a and b are separated so that the distance between a and b is at least radius(a) + radius(b).
 * To reduce jitter, this is by default a “soft” constraint with a configurable strength and iteration count.
 *
 * The generic refers to the type of data for a node.
 */
export interface ForceCollide<NodeDatum extends SimulationNodeDatum> extends Force<NodeDatum, any> {
    /**
     * Supplies the array of nodes and random source to this force. This method is called when a force is bound to a simulation via simulation.force
     * and when the simulation’s nodes change via simulation.nodes.
     *
     * A force may perform necessary work during initialization, such as evaluating per-node parameters, to avoid repeatedly performing work during each application of the force.
     */
    initialize(nodes: NodeDatum[], random: () => number): void;

    /**
     * Returns the current radius accessor function.
     */
    radius(): (node: NodeDatum, i: number, nodes: NodeDatum[]) => number;
    /**
     * Sets the radius accessor to the specified number or function, re-evaluates the radius accessor for each node, and returns this force.
     * The radius accessor is invoked for each node in the simulation, being passed the node and its zero-based index.
     * The resulting number is then stored internally, such that the radius of each node is only recomputed when the
     * force is initialized or when this method is called with a new radius, and not on every application of the force.
     */
    radius(radius: number | ((node: NodeDatum, i: number, nodes: NodeDatum[]) => number)): this;

    /**
     * Return the current strength, which defaults to 1.
     */
    strength(): number;
    /**
     * Set the force strength to the specified number in the range [0,1] and return this force.
     * The default strength is 1.
     *
     * Overlapping nodes are resolved through iterative relaxation.
     * For each node, the other nodes that are anticipated to overlap at the next tick (using the anticipated positions [x + vx,y + vy]) are determined;
     * the node’s velocity is then modified to push the node out of each overlapping node.
     * The change in velocity is dampened by the force’s strength such that the resolution of simultaneous overlaps can be blended together to find a stable solution.
     *
     * @param strength Strength.
     */
    strength(strength: number): this;

    /**
     * Return the current iteration count which defaults to 1.
     */
    iterations(): number;
    /**
     * Sets the number of iterations per application to the specified number and return this force.
     *
     * Increasing the number of iterations greatly increases the rigidity of the constraint and avoids partial overlap of nodes,
     * but also increases the runtime cost to evaluate the force.
     *
     * @param iterations Number of iterations.
     */
    iterations(iterations: number): this;
}

/**
 * Creates a new circle collision force with the specified radius.
 * If radius is not specified, it defaults to the constant one for all nodes.
 */
export function forceCollide<NodeDatum extends SimulationNodeDatum>(
    radius?: number | ((node: NodeDatum, i: number, nodes: NodeDatum[]) => number),
): ForceCollide<NodeDatum>;

// Link ----------------------------------------------------------------

/**
 * The link force pushes linked nodes together or apart according to the desired link distance.
 * The strength of the force is proportional to the difference between the linked nodes’ distance and the target distance, similar to a spring force.
 *
 * The first generic refers to the type of data for a node.
 * The second generic refers to the type of data for a link.
 */
export interface ForceLink<NodeDatum extends SimulationNodeDatum, LinkDatum extends SimulationLinkDatum<NodeDatum>>
    extends Force<NodeDatum, LinkDatum>
{
    /**
     * Supplies the array of nodes and random source to this force. This method is called when a force is bound to a simulation via simulation.force
     * and when the simulation’s nodes change via simulation.nodes.
     *
     * A force may perform necessary work during initialization, such as evaluating per-node parameters, to avoid repeatedly performing work during each application of the force.
     */
    initialize(nodes: NodeDatum[], random: () => number): void;

    /**
     * Return the current array of links, which defaults to the empty array.
     */
    links(): LinkDatum[];
    /**
     * Set the array of links associated with this force, recompute the distance and strength parameters for each link, and return this force.
     *
     * Each link is an object with the following properties:
     * * source - the link’s source node; see simulation.nodes
     * * target - the link’s target node; see simulation.nodes
     * * index - the zero-based index into links, assigned by this method
     *
     * For convenience, a link’s source and target properties may be initialized using numeric or string identifiers rather than object references; see link.id.
     * When the link force is initialized (or re-initialized, as when the nodes or links change), any link.source or link.target property which is not an object
     * is replaced by an object reference to the corresponding node with the given identifier.
     * If the specified array of links is modified, such as when links are added to or removed from the simulation,
     * this method must be called again with the new (or changed) array to notify the force of the change;
     * the force does not make a defensive copy of the specified array.
     *
     * @param links An array of link data.
     */
    links(links: LinkDatum[]): this;

    /**
     * Return the current node id accessor, which defaults to the numeric node.index.
     */
    id(): (node: NodeDatum, i: number, nodesData: NodeDatum[]) => string | number;
    /**
     * Set the node id accessor to the specified function and return this force.
     *
     * The default id accessor allows each link’s source and target to be specified as a zero-based index
     * into the nodes array.
     *
     * The id accessor is invoked for each node whenever the force is initialized,
     * as when the nodes or links change, being passed the node, the zero-based index of the node in the node array, and the node array.
     *
     * @param id A node id accessor function which is invoked for each node in the simulation,
     * being passed the node, the zero-based index of the node in the node array, and the node array. It returns a string or number to represent the node id which can be used
     * for matching link source and link target strings during the ForceLink initialization.
     */
    id(id: (node: NodeDatum, i: number, nodesData: NodeDatum[]) => string | number): this;

    /**
     * Return the current distance accessor, which defaults to implying a default distance of 30.
     */
    distance(): (link: LinkDatum, i: number, links: LinkDatum[]) => number;
    /**
     * Sets the distance accessor to the specified number or function, re-evaluates the distance accessor for each link, and returns this force.
     * The distance accessor is invoked for each link, being passed the link and its zero-based index.
     * The resulting number is then stored internally, such that the distance of each link is only recomputed when the
     * force is initialized or when this method is called with a new distance, and not on every application of the force.
     */
    distance(distance: number | ((link: LinkDatum, i: number, links: LinkDatum[]) => number)): this;

    /**
     * Return the current strength accessor.
     * For details regarding the default behavior see: {@link https://github.com/d3/d3-force#link_strength}
     */
    strength(): (link: LinkDatum, i: number, links: LinkDatum[]) => number;
    /**
     * Sets the strength accessor to the specified number or function, re-evaluates the strength accessor for each link, and returns this force.
     * The strength accessor is invoked for each link, being passed the link and its zero-based index.
     * The resulting number is then stored internally, such that the strength of each link is only recomputed when the
     * force is initialized or when this method is called with a new strength, and not on every application of the force.
     */
    strength(strength: number | ((link: LinkDatum, i: number, links: LinkDatum[]) => number)): this;

    /**
     * Return the current iteration count which defaults to 1.
     */
    iterations(): number;
    /**
     * Sets the number of iterations per application to the specified number and return this force.
     *
     * Increasing the number of iterations greatly increases the rigidity of the constraint and is useful for complex structures such as lattices,
     * but also increases the runtime cost to evaluate the force.
     *
     * @param iterations Number of iterations.
     */
    iterations(iterations: number): this;
}

/**
 * Creates a new link force with the specified links and default parameters.
 * If links is not specified, it defaults to the empty array.
 */
export function forceLink<NodeDatum extends SimulationNodeDatum, LinksDatum extends SimulationLinkDatum<NodeDatum>>(
    links?: LinksDatum[],
): ForceLink<NodeDatum, LinksDatum>;

// Many Body ----------------------------------------------------------------

/**
 * The many-body (or n-body) force applies mutually amongst all nodes. It can be used to simulate gravity (attraction) if the strength is positive,
 * or electrostatic charge (repulsion) if the strength is negative. This implementation uses quadtrees and the Barnes–Hut approximation to greatly
 * improve performance; the accuracy can be customized using the theta parameter.
 *
 * Unlike links, which only affect two linked nodes, the charge force is global: every node affects every other node, even if they are on disconnected subgraphs.
 *
 * The generic refers to the type of data for a node.
 */
export interface ForceManyBody<NodeDatum extends SimulationNodeDatum> extends Force<NodeDatum, any> {
    /**
     * Supplies the array of nodes and random source to this force. This method is called when a force is bound to a simulation via simulation.force
     * and when the simulation’s nodes change via simulation.nodes.
     *
     * A force may perform necessary work during initialization, such as evaluating per-node parameters, to avoid repeatedly performing work during each application of the force.
     */
    initialize(nodes: NodeDatum[], random: () => number): void;

    /**
     * Return the current strength accessor.
     *
     * For details regarding the default behavior see: {@link https://github.com/d3/d3-force#manyBody_strength}
     */
    strength(): (d: NodeDatum, i: number, data: NodeDatum[]) => number;
    /**
     * sets the strength accessor to the specified number or function, re-evaluates the strength accessor for each node, and returns this force.
     * A positive value causes nodes to attract each other, similar to gravity, while a negative value causes nodes to repel each other, similar to electrostatic charge.
     * The strength accessor is invoked for each node in the simulation, being passed the node and its zero-based index.
     * The resulting number is then stored internally, such that the strength of each node is only recomputed when the
     * force is initialized or when this method is called with a new strength, and not on every application of the force.
     */
    strength(strength: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number)): this;

    /**
     * Return the current value of the Barnes–Hut approximation criterion , which defaults to 0.9
     */
    theta(): number;
    /**
     * Set the Barnes–Hut approximation criterion to the specified number and returns this force.
     *
     * To accelerate computation, this force implements the Barnes–Hut approximation which takes O(n log n) per application
     * where n is the number of nodes. For each application, a quadtree stores the current node positions;
     * then for each node, the combined force of all other nodes on the given node is computed.
     * For a cluster of nodes that is far away, the charge force can be approximated by treating the cluster as a single, larger node.
     * The theta parameter determines the accuracy of the approximation:
     * if the ratio w / l of the width w of the quadtree cell to the distance l from the node to the cell’s center of mass is less than theta,
     * all nodes in the given cell are treated as a single node rather than individually.
     *
     * The default value is 0.9.
     *
     * @param theta Value for the theta parameter.
     */
    theta(theta: number): this;

    /**
     * Returns the current minimum distance over which this force is considered, which defaults to 1.
     */
    distanceMin(): number;
    /**
     * Sets the minimum distance between nodes over which this force is considered.
     *
     * A minimum distance establishes an upper bound on the strength of the force between two nearby nodes, avoiding instability.
     * In particular, it avoids an infinitely-strong force if two nodes are exactly coincident; in this case, the direction of the force is random.
     *
     * The default value is 1.
     *
     * @param distance The minimum distance between nodes over which this force is considered.
     */
    distanceMin(distance: number): this;

    /**
     * Returns the current maximum distance over which this force is considered, which defaults to infinity.
     */
    distanceMax(): number;
    /**
     * Sets the maximum distance between nodes over which this force is considered.
     *
     * Specifying a finite maximum distance improves performance and produces a more localized layout.
     *
     * The default value is infinity.
     *
     * @param distance The maximum distance between nodes over which this force is considered.
     */
    distanceMax(distance: number): this;
}

/**
 * Creates a new many-body force with the default parameters.
 *
 * The many-body (or n-body) force applies mutually amongst all nodes. It can be used to simulate gravity (attraction) if the strength is positive,
 * or electrostatic charge (repulsion) if the strength is negative. This implementation uses quadtrees and the Barnes–Hut approximation to greatly
 * improve performance; the accuracy can be customized using the theta parameter.
 *
 * Unlike links, which only affect two linked nodes, the charge force is global: every node affects every other node, even if they are on disconnected subgraphs.
 *
 * The generic refers to the type of data for a node.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function forceManyBody<NodeDatum extends SimulationNodeDatum>(): ForceManyBody<NodeDatum>;

// Positioning ----------------------------------------------------------------

/**
 * The x-positioning force pushes nodes towards a desired position along the given dimension with a configurable strength.
 * The strength of the force is proportional to the one-dimensional distance between the node’s position and the target position.
 * While this force can be used to position individual nodes, it is intended primarily for global forces that apply to all (or most) nodes.
 *
 * The generic refers to the type of data for a node.
 */
export interface ForceX<NodeDatum extends SimulationNodeDatum> extends Force<NodeDatum, any> {
    /**
     * Supplies the array of nodes and random source to this force. This method is called when a force is bound to a simulation via simulation.force
     * and when the simulation’s nodes change via simulation.nodes.
     *
     * A force may perform necessary work during initialization, such as evaluating per-node parameters, to avoid repeatedly performing work during each application of the force.
     */
    initialize(nodes: NodeDatum[], random: () => number): void;

    /**
     *  Returns the current strength accessor, which defaults to a constant strength for all nodes of 0.1.
     */
    strength(): (d: NodeDatum, i: number, data: NodeDatum[]) => number;
    /**
     * Sets the strength accessor to the specified number or function, re-evaluates the strength accessor for each node, and returns this force.
     * The strength determines how much to increment the node’s x-velocity: (x - node.x) × strength.
     * For example, a value of 0.1 indicates that the node should move a tenth of the way from its current x-position to the target x-position with each application.
     * Higher values moves nodes more quickly to the target position, often at the expense of other forces or constraints.
     * A value outside the range [0,1] is not recommended.
     * The strength accessor is invoked for each node in the simulation, being passed the node and its zero-based index.
     * The resulting number is then stored internally, such that the strength of each node is only recomputed when the
     * force is initialized or when this method is called with a new strength, and not on every application of the force.
     */
    strength(strength: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number)): this;

    /**
     * Return the current x-accessor, which defaults to a function returning 0 for all nodes.
     */
    x(): (d: NodeDatum, i: number, data: NodeDatum[]) => number;
    /**
     * Sets the x-coordinate accessor to the specified number or function, re-evaluates the x-accessor for each node, and returns this force.
     * The x-accessor is invoked for each node in the simulation, being passed the node and its zero-based index.
     * The resulting number is then stored internally, such that the target x-coordinate of each node is only recomputed
     * when the force is initialized or when this method is called with a new x, and not on every application of the force.
     */
    x(x: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number)): this;
}

/**
 * Creates a new positioning force along the x-axis towards the given position x.
 * If x is not specified, it defaults to 0.
 */
export function forceX<NodeDatum extends SimulationNodeDatum>(
    x?: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number),
): ForceX<NodeDatum>;

/**
 * The y-positioning force pushes nodes towards a desired position along the given dimension with a configurable strength.
 * The strength of the force is proportional to the one-dimensional distance between the node’s position and the target position.
 * While this force can be used to position individual nodes, it is intended primarily for global forces that apply to all (or most) nodes.
 *
 * The generic refers to the type of data for a node.
 */
export interface ForceY<NodeDatum extends SimulationNodeDatum> extends Force<NodeDatum, any> {
    /**
     * Supplies the array of nodes and random source to this force. This method is called when a force is bound to a simulation via simulation.force
     * and when the simulation’s nodes change via simulation.nodes.
     *
     * A force may perform necessary work during initialization, such as evaluating per-node parameters, to avoid repeatedly performing work during each application of the force.
     */
    initialize(nodes: NodeDatum[], random: () => number): void;

    /**
     *  Returns the current strength accessor, which defaults to a constant strength for all nodes of 0.1.
     */
    strength(): (d: NodeDatum, i: number, data: NodeDatum[]) => number;
    /**
     * Sets the strength accessor to the specified number or function, re-evaluates the strength accessor for each node, and returns this force.
     * The strength determines how much to increment the node’s y-velocity: (y - node.y) × strength.
     * For example, a value of 0.1 indicates that the node should move a tenth of the way from its current y-position to the target y-position with each application.
     * Higher values moves nodes more quickly to the target position, often at the expense of other forces or constraints.
     * A value outside the range [0,1] is not recommended.
     * The strength accessor is invoked for each node in the simulation, being passed the node and its zero-based index.
     * The resulting number is then stored internally, such that the strength of each node is only recomputed when the
     * force is initialized or when this method is called with a new strength, and not on every application of the force.
     */
    strength(strength: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number)): this;

    /**
     * Return the current y-accessor, which defaults to a function returning 0 for all nodes.
     */
    y(): (d: NodeDatum, i: number, data: NodeDatum[]) => number;
    /**
     * Sets the y-coordinate accessor to the specified number or function, re-evaluates the y-accessor for each node, and returns this force.
     * The y-accessor is invoked for each node in the simulation, being passed the node and its zero-based index.
     * The resulting number is then stored internally, such that the target y-coordinate of each node is only recomputed
     * when the force is initialized or when this method is called with a new y, and not on every application of the force.
     */
    y(y: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number)): this;
}

/**
 * Creates a new positioning force along the y-axis towards the given position y.
 * If y is not specified, it defaults to 0.
 */
export function forceY<NodeDatum extends SimulationNodeDatum>(
    y?: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number),
): ForceY<NodeDatum>;

/**
 * The radial force is similar to the x- and y-positioning forces, except it pushes nodes towards the closest point on a given circle.
 * The circle is of the specified radius centered at ⟨x,y⟩. If x and y are not specified, they default to ⟨0,0⟩.
 * The strength of the force is proportional to the one-dimensional distance between the node’s position and the target position.
 * While this force can be used to position individual nodes, it is intended primarily for global forces that apply to all (or most) nodes.
 *
 * The generic refers to the type of data for a node.
 */
export interface ForceRadial<NodeDatum extends SimulationNodeDatum> extends Force<NodeDatum, any> {
    /**
     * Assigns the array of nodes and random source to this force. This method is called when a force is bound to a simulation via simulation.force
     * and when the simulation’s nodes change via simulation.nodes.
     *
     * A force may perform necessary work during initialization, such as evaluating per-node parameters, to avoid repeatedly performing work during each application of the force.
     */
    initialize(nodes: NodeDatum[], random: () => number): void;

    /**
     *  Returns the current strength accessor, which defaults to a constant strength for all nodes of 0.1.
     */
    strength(): (d: NodeDatum, i: number, data: NodeDatum[]) => number;
    /**
     * Sets the strength accessor to the specified number or function, re-evaluates the strength accessor for each node, and returns this force.
     * The strength determines how much to increment the node’s x- and y-velocity.
     * For example, a value of 0.1 indicates that the node should move a tenth of the way from its current position to the closest point on the circle with each application.
     * Higher values moves nodes more quickly to the target position, often at the expense of other forces or constraints.
     * A value outside the range [0,1] is not recommended.
     * The strength accessor is invoked for each node in the simulation, being passed the node and its zero-based index.
     * The resulting number is then stored internally, such that the strength of each node is only recomputed when the
     * force is initialized or when this method is called with a new strength, and not on every application of the force.
     */
    strength(strength: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number)): this;

    /**
     * Return the current radius accessor for the circle.
     */
    radius(): (d: NodeDatum, i: number, data: NodeDatum[]) => number;
    /**
     * Sets the circle radius to the specified number or function, re-evaluates the radius accessor for each node, and returns this force.
     * The radius accessor is invoked for each node in the simulation, being passed the node and its zero-based index.
     * The resulting number is then stored internally, such that the target radius of each node is only recomputed when
     * the force is initialized or when this method is called with a new radius, and not on every application of the force.
     */
    radius(radius: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number)): this;

    /**
     * Return the current x-accessor for the circle center, which defaults to a function returning 0 for all nodes.
     */
    x(): (d: NodeDatum, i: number, data: NodeDatum[]) => number;
    /**
     * Sets the x-coordinate of the circle center to the specified number and returns this force.
     */
    x(x: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number)): this;

    /**
     * Return the current y-accessor for the circle center, which defaults to a function returning 0 for all nodes.
     */
    y(): (d: NodeDatum, i: number, data: NodeDatum[]) => number;
    /**
     * Sets the y-coordinate of the circle center to the specified number and returns this force.
     */
    y(y: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number)): this;
}

/**
 * Create a new radial positioning force towards a circle of the specified radius centered at ⟨x,y⟩.
 * If x and y are not specified, they default to ⟨0,0⟩.
 *
 * The strength of the force is proportional to the one-dimensional distance between the node’s position and the target position.
 * While this force can be used to position individual nodes, it is intended primarily for global forces that apply to all (or most) nodes.
 *
 * The generic refers to the type of data for a node.
 */
export function forceRadial<NodeDatum extends SimulationNodeDatum>(
    radius: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number),
    x?: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number),
    y?: number | ((d: NodeDatum, i: number, data: NodeDatum[]) => number),
): ForceRadial<NodeDatum>;
