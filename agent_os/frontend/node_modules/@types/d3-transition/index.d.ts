// Last module patch version validated against: 3.0.1

import { ArrayLike, BaseType, Selection, ValueFn } from "d3-selection";

/**
 * Extend interface 'Selection' by declaration merging with 'd3-selection'
 */
declare module "d3-selection" {
    /**
     * A D3 Selection of elements.
     *
     * The first generic "GElement" refers to the type of the selected element(s).
     * The second generic "Datum" refers to the type of the datum of a selected element(s).
     * The third generic "PElement" refers to the type of the parent element(s) in the D3 selection.
     * The fourth generic "PDatum" refers to the type of the datum of the parent element(s).
     */
    interface Selection<GElement extends BaseType, Datum, PElement extends BaseType, PDatum> {
        /**
         * Interrupts the active transition of the specified name on the selected elements, and cancels any pending transitions with the specified name, if any.
         * If a name is not specified, null is used.
         *
         * IMPORTANT: Interrupting a transition on an element has no effect on any transitions on any descendant elements.
         * For example, an axis transition consists of multiple independent, synchronized transitions on the descendants of the axis G element
         * (the tick lines, the tick labels, the domain path, etc.). To interrupt the axis transition, you must therefore interrupt the descendants.
         *
         * @param name Name of the transition.
         */
        interrupt(name?: string): this;
        /**
         * Returns a new transition on the given selection with the specified name. If a name is not specified, null is used.
         * The new transition is only exclusive with other transitions of the same name.
         *
         * @param name Name of the transition.
         */
        transition(name?: string): Transition<GElement, Datum, PElement, PDatum>;
        /**
         * Returns a new transition on the given selection.
         *
         * When using a transition instance, the returned transition has the same id and name as the specified transition.
         * If a transition with the same id already exists on a selected element, the existing transition is returned for that element.
         * Otherwise, the timing of the returned transition is inherited from the existing transition of the same id on the nearest ancestor of each selected element.
         * Thus, this method can be used to synchronize a transition across multiple selections,
         * or to re-select a transition for specific elements and modify its configuration.
         *
         * If the specified transition is not found on a selected node or its ancestors (such as if the transition already ended),
         * the default timing parameters are used; however, in a future release, this will likely be changed to throw an error.
         *
         * @param transition A transition instance.
         */
        transition(transition: Transition<BaseType, any, any, any>): Transition<GElement, Datum, PElement, PDatum>;
    }
}

/**
 * Return the active transition on the specified node with the specified name, if any.
 * If no name is specified, null is used. Returns null if there is no such active transition on the specified node.
 * This method is useful for creating chained transitions.
 *
 * The first generic "GElement" refers to the type of element on which the returned active transition was defined. The second generic "Datum" refers to the type of the
 * datum, of a selected element on which the transition is defined. The third generic refers to the type of the parent elements in the returned Transition.
 * The fourth generic refers to the type of the datum defined on the parent elements in the returned Transition.
 *
 * @param node Element for which the active transition should be returned.
 * @param name Name of the transition.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function active<GElement extends BaseType, Datum, PElement extends BaseType, PDatum>(
    node: GElement,
    name?: string,
): Transition<GElement, Datum, PElement, PDatum> | null;

/**
 * Interrupts the active transition of the specified name on the specified node, and cancels any pending transitions with the specified name, if any.
 * If a name is not specified, null is used.
 *
 * @param node Element for which the transition should be interrupted.
 * @param name Name of the transition to be interrupted. If a name is not specified, null is used.
 */
export function interrupt(node: BaseType, name?: string): void;

/**
 * A D3 Transition.
 *
 * The first generic "GElement" refers to the type of the selected element(s) in the Transition.
 * The second generic "Datum" refers to the type of the datum of a selected element(s) in the Transition.
 * The third generic "PElement" refers to the type of the parent element(s) in the D3 selection in the Transition.
 * The fourth generic "PDatum" refers to the type of the datum of the parent element(s) in the Transition.
 */
export interface Transition<GElement extends BaseType, Datum, PElement extends BaseType, PDatum> {
    // Sub-selection -------------------------

    /**
     * For each selected element, select the first descendant element that matches the specified selector string, if any,
     * and returns a transition on the resulting selection. The new transition has the same id, name and timing as this transition;
     * however, if a transition with the same id already exists on a selected element,
     * the existing transition is returned for that element.
     *
     * The generic represents the type of the descendant element to be selected.
     *
     * @param selector CSS selector string
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    select<DescElement extends BaseType>(selector: string): Transition<DescElement, Datum, PElement, PDatum>;
    /**
     * For each selected element, select the descendant element returned by the selector function, if any,
     * and returns a transition on the resulting selection. The new transition has the same id, name and timing as this transition;
     * however, if a transition with the same id already exists on a selected element,
     * the existing transition is returned for that element.
     *
     * The generic represents the type of the descendant element to be selected.
     *
     * @param selector A selector function, which is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]).
     * It must return an element, or null if there is no matching element.
     */
    select<DescElement extends BaseType>(
        selector: ValueFn<GElement, Datum, DescElement>,
    ): Transition<DescElement, Datum, PElement, PDatum>;

    /**
     * For each selected element, select all descendant elements that match the specified selector string, if any,
     * and returns a transition on the resulting selection. The new transition has the same id, name and timing as this transition;
     * however, if a transition with the same id already exists on a selected element, the existing transition is returned for that element.
     *
     * The first generic "DescElement" refers to the type of descendant element to be selected. The second generic "OldDatum" refers to the type of the
     * datum, of a selected element. This is useful when re-selecting elements with a previously set, know datum type.
     *
     * @param selector CSS selector string
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    selectAll<DescElement extends BaseType, OldDatum>(
        selector: string,
    ): Transition<DescElement, OldDatum, GElement, Datum>;
    /**
     * For each selected element, select all descendant elements returned by the selector function, if any,
     * and returns a transition on the resulting selection. The new transition has the same id, name and timing as this transition;
     * however, if a transition with the same id already exists on a selected element, the existing transition is returned for that element.
     *
     * The first generic "DescElement" refers to the type of descendant element to be selected. The second generic "OldDatum" refers to the type of the
     * datum, of a selected element. This is useful when re-selecting elements with a previously set, know datum type.
     *
     * @param selector A selector function which is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]). It must return an array of elements
     * (or a pseudo-array, such as a NodeList), or the empty array if there are no matching elements.
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    selectAll<DescElement extends BaseType, OldDatum>(
        selector: ValueFn<GElement, Datum, DescElement[] | ArrayLike<DescElement>>,
    ): Transition<DescElement, OldDatum, GElement, Datum>;

    /**
     * For each selected element, selects the first child element that matches the specified selector string, if any, and returns a transition on the resulting selection.
     * The selector may be specified either as a selector string or a function.
     * If a function, it is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element.
     * The new transition has the same id, name and timing as this transition;
     * however, if a transition with the same id already exists on a selected element, the existing transition is returned for that element.
     * This method is equivalent to deriving the selection for this transition via transition.selection,
     * creating a subselection via selection.selectChild, and then creating a new transition via selection.transition.
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    selectChild<DescElement extends BaseType, OldDatum>(
        selector?: string | ValueFn<GElement, Datum, DescElement>,
    ): Transition<DescElement, OldDatum, GElement, Datum>;

    /**
     * For each selected element, selects all children that match the specified selector string, if any, and returns a transition on the resulting selection.
     * The selector may be specified either as a selector string or a function.
     * If a function, it is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element.
     * The new transition has the same id, name and timing as this transition;
     * however, if a transition with the same id already exists on a selected element, the existing transition is returned for that element.
     * This method is equivalent to deriving the selection for this transition via transition.selection,
     * creating a subselection via selection.selectChildren, and then creating a new transition via selection.transition.
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    selectChildren<DescElement extends BaseType, OldDatum>(
        selector?: string | ValueFn<GElement, Datum, DescElement>,
    ): Transition<DescElement, OldDatum, GElement, Datum>;

    /**
     * Return the selection corresponding to this transition.
     */
    selection(): Selection<GElement, Datum, PElement, PDatum>;

    /**
     * Returns a new transition on the same selected elements as this transition, scheduled to start when this transition ends.
     * The new transition inherits a reference time equal to this transition’s time plus its delay and duration.
     * The new transition also inherits this transition’s name, duration, and easing.
     * This method can be used to schedule a sequence of chained transitions.
     *
     * A delay configured for the new transition will be relative to the previous transition.
     */
    transition(): Transition<GElement, Datum, PElement, PDatum>;

    // Modifying -------------------------------

    /**
     * For each selected element, assigns the attribute tween for the attribute with the specified name to the specified target value.
     * The starting value of the tween is the attribute’s value when the transition starts.
     * If the target value is null, the attribute is removed when the transition starts.
     */
    attr(name: string, value: null | string | number | boolean): this;
    /**
     * For each selected element, assigns the attribute tween for the attribute with the specified name to the specified target value.
     * The starting value of the tween is the attribute’s value when the transition starts.
     * The target value is return value of the value function evaluated for the selected element.
     *
     * An interpolator is chosen based on the type of the target value, using the following algorithm:
     * 1.) If value is a number, use interpolateNumber.
     * 2.) If value is a color or a string coercible to a color, use interpolateRgb.
     * 3.) Use interpolateString.
     *
     * To apply a different interpolator, use transition.attrTween.
     *
     * @param name Name of the attribute.
     * @param value A value function which is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]).
     * A null value will clear the attribute at the start of the transition.
     */
    attr(name: string, value: ValueFn<GElement, Datum, string | number | boolean | null>): this;

    /**
     * Return the current interpolator factory for attribute with the specified name, or undefined if no such tween exists.
     *
     * @param name Name of attribute.
     */
    attrTween(name: string): ValueFn<GElement, Datum, (this: GElement, t: number) => string> | undefined;
    /**
     * Remove the previously-assigned attribute tween of the specified name, if any.
     *
     * @param name Name of attribute.
     * @param factory Use null to remove previously-assigned attribute tween.
     */
    attrTween(name: string, factory: null): this;
    /**
     * Assign the attribute tween for the attribute with the specified name to the specified interpolator factory.
     * An interpolator factory is a function that returns an interpolator; when the transition starts, the factory is evaluated for each selected element.
     * The returned interpolator will then be invoked for each frame of the transition, in order,
     * being passed the eased time t, typically in the range [0, 1]. Lastly, the return value of the interpolator will be used to set the attribute value.
     * The interpolator must return a string.
     *
     * @param name Name of attribute.
     * @param factory An interpolator factory which is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]). The interpolator factory returns a string interpolator,
     * which takes as its argument eased time t, typically in the range [0, 1] and returns the interpolated string.
     */
    attrTween(name: string, factory: ValueFn<GElement, Datum, (this: GElement, t: number) => string>): this;

    /**
     * For each selected element, the style with the specified name will be cleared at the start of the transition.
     *
     * @param name Name of the style.
     * @param value Use null to clear the style.
     */
    style(name: string, value: null): this;
    /**
     * For each selected element, assigns the style tween for the style with the specified name to the specified target value with the
     * specified priority.
     * The starting value of the tween is the style’s inline value if present, and otherwise its computed value.
     * The target value is the specified constant value for all elements.
     *
     * An interpolator is chosen based on the type of the target value, using the following algorithm:
     * 1.) If value is a number, use interpolateNumber.
     * 2.) If value is a color or a string coercible to a color, use interpolateRgb.
     * 3.) Use interpolateString.
     *
     * To apply a different interpolator, use transition.attrTween.
     *
     * @param name Name of the style.
     * @param value Target value for the style.
     * @param priority An optional priority flag, either null or the string important (without the exclamation point)
     */
    style(name: string, value: string | number | boolean, priority?: null | "important"): this;
    /**
     * For each selected element, assigns the style tween for the style with the specified name to the specified target value with the
     * specified priority.
     * The starting value of the tween is the style's inline value if present, and otherwise its computed value.
     * The target value is return value of the value function evaluated for the selected element.
     *
     * An interpolator is chosen based on the type of the target value, using the following algorithm:
     * 1.) If value is a number, use interpolateNumber.
     * 2.) If value is a color or a string coercible to a color, use interpolateRgb.
     * 3.) Use interpolateString.
     *
     * To apply a different interpolator, use transition.attrTween.
     *
     * @param name Name of the style.
     * @param value A value function which is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]).
     * A null value will clear the style at the start of the transition.
     * @param priority An optional priority flag, either null or the string important (without the exclamation point)
     */
    style(
        name: string,
        value: ValueFn<GElement, Datum, string | number | boolean | null>,
        priority?: null | "important",
    ): this;

    /**
     * Return the current interpolator factory for style with the specified name, or undefined if no such tween exists.
     *
     * @param name Name of style.
     */
    styleTween(name: string): ValueFn<GElement, Datum, (this: GElement, t: number) => string> | undefined;
    /**
     * Remove the previously-assigned style tween of the specified name, if any.
     *
     * @param name Name of style.
     * @param factory Use null to remove previously-assigned style tween.
     */
    styleTween(name: string, factory: null): this;
    /**
     * Assign the style tween for the style with the specified name to the specified interpolator factory.
     * An interpolator factory is a function that returns an interpolator; when the transition starts, the factory is evaluated for each selected element.
     * The returned interpolator will then be invoked for each frame of the transition, in order,
     * being passed the eased time t, typically in the range [0, 1]. Lastly, the return value of the interpolator will be used to set the style value.
     * The interpolator must return a string.
     *
     * @param name Name of style.
     * @param factory An interpolator factory which is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]). The interpolator factory returns a string interpolator,
     * which takes as its argument eased time t, typically in the range [0, 1] and returns the interpolated string.
     * @param priority An optional priority flag, either null or the string important (without the exclamation point)
     */
    styleTween(
        name: string,
        factory: ValueFn<GElement, Datum, (this: GElement, t: number) => string>,
        priority?: null | "important",
    ): this;

    /**
     * For each selected element, sets the text content to the specified target value when the transition starts.
     * A null value will clear the content.
     */
    text(value: null | string | number | boolean): this;
    /**
     * For each selected element, sets the text content returned by the value function for each selected element when the transition starts.
     *
     * To interpolate text rather than to set it on start, use transition.textTween (for example) or append a replacement element and cross-fade opacity (for example).
     * Text is not interpolated by default because it is usually undesirable.
     *
     * @param value A value function which is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]).
     * A null value will clear the text content at the start of the transition.
     */
    text(value: ValueFn<GElement, Datum, string | number | boolean>): this;

    /**
     * Returns the current interpolator factory for text, or undefined if no such tween exists.
     */
    textTween(): ValueFn<GElement, Datum, (this: GElement, t: number) => string> | undefined;
    /**
     * Removes the previously-assigned text tween, if any
     *
     * @param factory Use null to remove previously-assigned text tween.
     */
    textTween(factory: null): this;
    /**
     * Assigns the text tween to the specified interpolator factory.
     * An interpolator factory is a function that returns an interpolator; when the transition starts, the factory is evaluated for each selected element,
     * in order, being passed the current datum d and index i, with the this context as the current DOM element.
     * The returned interpolator will then be invoked for each frame of the transition, in order, being passed the eased time t, typically in the range [0, 1].
     * Lastly, the return value of the interpolator will be used to set the text.
     * The interpolator must return a string.
     *
     * @param factory An interpolator factory is a function that returns an interpolator; when the transition starts, the factory is evaluated for each selected element,
     * in order, being passed the current datum d and index i, with the this context as the current DOM element.
     * The returned interpolator will then be invoked for each frame of the transition, in order, being passed the eased time t, typically in the range [0, 1].
     * Lastly, the return value of the interpolator will be used to set the text.
     * The interpolator must return a string.
     */
    textTween(factory: ValueFn<GElement, Datum, (this: GElement, t: number) => string>): this;

    /**
     * For each selected element, removes the element when the transition ends, as long as the element has no other active or pending transitions.
     * If the element has other active or pending transitions, does nothing.
     */
    remove(): this;

    /**
     * Returns the tween with the specified name, or undefined, if no tween was previously assigned to
     * that name.
     *
     * @param name Name of tween.
     */
    tween(name: string): ValueFn<GElement, Datum, (this: GElement, t: number) => void> | undefined;
    /**
     * Removes the tween with the specified name, if a tween was previously assigned to
     * that name.
     *
     * @param name Name of tween.
     * @param tweenFn Use null to remove a previously-assigned tween.
     */
    tween(name: string, tweenFn: null): this;
    /**
     * For each selected element, assigns the tween with the specified name with the specified value function.
     * The value must be specified as a function that returns a function.
     * When the transition starts, the value function is evaluated for each selected element.
     * The returned function is then invoked for each frame of the transition, in order,
     * being passed the eased time t, typically in the range [0, 1].
     *
     * @param name Name of tween.
     * @param tweenFn A tween function which is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]). The tween function returns a function
     * which takes as its argument eased time t, typically in the range [0, 1] and performs the tweening activities for each transition frame.
     */
    tween(name: string, tweenFn: ValueFn<GElement, Datum, (this: GElement, t: number) => void>): this;

    /**
     * Returns a new transition merging this transition with the specified other transition,
     * which must have the same id as this transition. The returned transition has the same number of groups,
     * the same parents, the same name and the same id as this transition.
     * Any missing (null) elements in this transition are filled with the corresponding element, if present (not null), from the other transition.
     *
     * @param other The transition to be merged.
     */
    merge(other: Transition<GElement, Datum, PElement, PDatum>): Transition<GElement, Datum, PElement, PDatum>;

    /**
     * For each selected element, selects only the elements that match the specified filter, and returns a transition on the resulting selection.
     *
     * The new transition has the same id, name and timing as this transition; however, if a transition with the same id already exists on a selected element,
     * the existing transition is returned for that element.
     *
     * @param filter A CSS selector string.
     */
    filter(filter: string): Transition<GElement, Datum, PElement, PDatum>;
    /**
     * For each selected element, selects only the elements that match the specified filter, and returns a transition on the resulting selection.
     *
     * The new transition has the same id, name and timing as this transition; however, if a transition with the same id already exists on a selected element,
     * the existing transition is returned for that element.
     *
     * The generic refers to the type of element which will be selected after applying the filter, i.e. if the element types
     * contained in a pre-filter selection are narrowed to a subset as part of the filtering.
     *
     * @param filter A CSS selector string.
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    filter<FilteredElement extends BaseType>(filter: string): Transition<FilteredElement, Datum, PElement, PDatum>;
    /**
     * For each selected element, selects only the elements that match the specified filter, and returns a transition on the resulting selection.
     *
     * The new transition has the same id, name and timing as this transition; however, if a transition with the same id already exists on a selected element,
     * the existing transition is returned for that element.
     *
     * @param filter A filter function which is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]). The filter function returns a boolean indicating,
     * whether the selected element matches.
     */
    filter(filter: ValueFn<GElement, Datum, boolean>): Transition<GElement, Datum, PElement, PDatum>;
    /**
     * For each selected element, selects only the elements that match the specified filter, and returns a transition on the resulting selection.
     *
     * The new transition has the same id, name and timing as this transition; however, if a transition with the same id already exists on a selected element,
     * the existing transition is returned for that element.
     *
     * The generic refers to the type of element which will be selected after applying the filter, i.e. if the element types
     * contained in a pre-filter selection are narrowed to a subset as part of the filtering.
     *
     * @param filter A filter function which is evaluated for each selected element, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]). The filter function returns a boolean indicating,
     * whether the selected element matches.
     */
    // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
    filter<FilteredElement extends BaseType>(
        filter: ValueFn<GElement, Datum, boolean>,
    ): Transition<FilteredElement, Datum, PElement, PDatum>;

    // Event Handling -------------------

    /**
     * Return the currently-assigned listener for the specified event typename on the first (non-null) selected element, if any.
     * If multiple typenames are specified, the first matching listener is returned.
     *
     * @param typenames The typenames is one of the following string event types: start (when the transition starts), end (when the transition ends),
     * interrupt (when the transition is interrupted), cancel(when the transition is cancelled).
     * Note that these are not native DOM events. The type may be optionally followed by a period (.) and a name;
     * the optional name allows multiple callbacks to be registered to receive events of the same type, such as "start.foo"" and "start.bar".
     * To specify multiple typenames, separate typenames with spaces, such as "interrupt end"" or "start.foo start.bar".
     */
    on(typenames: string): ValueFn<GElement, Datum, void> | undefined;
    /**
     * Remove all listeners for a given name.
     *
     * @param typenames Name of the event type for which the listener should be removed. To remove all listeners for a given name use ".foo"
     * as the typename, where foo is the name; to remove all listeners with no name, specify "." as the typename.
     * @param listener Use null to remove listeners.
     */
    on(typenames: string, listener: null): this;
    /**
     * Add a listener to each selected element for the specified event typenames.
     *
     * When a specified transition event is dispatched on a selected node, the specified listener will be invoked for each transitioning element.
     * Listeners always see the latest datum for their element, but the index is a property of the selection and is fixed when the listener is assigned;
     * to update the index, re-assign the listener.
     *
     * @param typenames The typenames is one of the following string event types: start (when the transition starts), end (when the transition ends),
     * interrupt (when the transition is interrupted), cancel(when the transition is cancelled).
     * Note that these are not native DOM events. The type may be optionally followed by a period (.) and a name;
     * the optional name allows multiple callbacks to be registered to receive events of the same type, such as "start.foo"" and "start.bar".
     * To specify multiple typenames, separate typenames with spaces, such as "interrupt end"" or "start.foo start.bar".
     * @param listener A listener function which will be evaluated for each selected element, being passed the current datum (d), the current index (i),
     * and the current group (nodes), with this as the current DOM element (nodes[i]). Listeners always see the latest datum for their element,
     * but the index is a property of the selection and is fixed when the listener is assigned; to update the index, re-assign the listener.
     */
    on(typenames: string, listener: ValueFn<GElement, Datum, void>): this;

    /**
     * Returns a promise that resolves when every selected element finishes transitioning. If any element’s transition is cancelled or interrupted, the promise rejects.
     */
    end(): Promise<void>;

    // Control Flow ----------------------

    /**
     * Invoke the specified function for each selected element, passing the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]).
     * This method can be used to invoke arbitrary code for each selected element, and is useful for creating a context to access parent and child data simultaneously.
     *
     * @param func A function which is invoked for each selected element,
     *             being passed the current datum (d), the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]).
     */
    each(func: ValueFn<GElement, Datum, void>): this;

    /**
     * Invoke the specified function exactly once, passing in this transition along with any optional arguments.
     * Returns this transition.
     *
     * @param func A function which is passed this transition as the first argument along with any optional arguments.
     * @param args List of optional arguments to be passed to the callback function.
     */
    call(
        func: (transition: Transition<GElement, Datum, PElement, PDatum>, ...args: any[]) => any,
        ...args: any[]
    ): this;

    /**
     * Return true if this transition contains no (non-null) elements.
     */
    empty(): boolean;

    /**
     * Return the first (non-null) element in this transition. If the transition is empty, returns null.
     */
    node(): GElement | null;

    /**
     * Return an array of all (non-null) elements in this transition.
     */
    nodes(): GElement[];

    /**
     * Returns the total number of elements in this transition.
     */
    size(): number;

    // Transition Configuration ----------------------

    /**
     * Returns the current value of the delay for the first (non-null) element in the transition.
     * This is generally useful only if you know that the transition contains exactly one element.
     */
    delay(): number;
    /**
     * For each selected element, sets the transition delay to the specified value in milliseconds.
     * If a delay is not specified, it defaults to zero.
     *
     * @param milliseconds Number of milliseconds for the delay.
     */
    delay(milliseconds: number): this;
    /**
     * For each selected element, sets the transition delay to the value in milliseconds returned by the
     * value function.
     *
     * @param milliseconds A value function which is evaluated for each selected element, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]). The return value is a number
     * specifying the delay in milliseconds.
     */
    delay(milliseconds: ValueFn<GElement, Datum, number>): this;

    /**
     * Returns the current value of the duration for the first (non-null) element in the transition.
     * This is generally useful only if you know that the transition contains exactly one element.
     */
    duration(): number;
    /**
     * For each selected element, sets the transition duration to the specified value in milliseconds.
     * If a duration is not specified, it defaults to 250ms.
     *
     * @param duration Number of milliseconds for the duration.
     */
    duration(milliseconds: number): this;
    /**
     * For each selected element, sets the transition duration to the value in milliseconds returned by the
     * value function.
     *
     * @param milliseconds A value function which is evaluated for each selected element, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element (nodes[i]). The return value is a number
     * specifying the duration in milliseconds.
     */
    duration(milliseconds: ValueFn<GElement, Datum, number>): this;

    /**
     * Returns the current easing function for the first (non-null) element in the transition.
     * This is generally useful only if you know that the transition contains exactly one element.
     */
    ease(): (normalizedTime: number) => number;
    /**
     * Specifies the transition easing function for all selected elements. The value must be specified as a function.
     * The easing function is invoked for each frame of the animation, being passed the normalized time t in the range [0, 1];
     * it must then return the eased time tʹ which is typically also in the range [0, 1].
     * A good easing function should return 0 if t = 0 and 1 if t = 1. If an easing function is not specified,
     * it defaults to d3.easeCubic.
     *
     * @param easingFn An easing function which is passed the normalized time t in the range [0, 1];
     * it must then return the eased time tʹ which is typically also in the range [0, 1].
     * A good easing function should return 0 if t = 0 and 1 if t = 1.
     */
    ease(easingFn: (normalizedTime: number) => number): this;

    /**
     * Specifies a factory for the transition easing function.
     *
     * @param factory The factory must be a function.
     * It is invoked for each node of the selection, being passed the current datum (d), the current index (i), and the current group (nodes), with this as the current DOM element.
     * It must return an easing function.
     */
    easeVarying(factory: ValueFn<GElement, Datum, (normalizedTime: number) => number>): this;
}

/**
 * Represents the union of the Selection and Transition types for any usages that operate on both.
 * Typically used for functions which take in either a selection or transition and set or update attributes.
 */
export type SelectionOrTransition<GElement extends BaseType, Datum, PElement extends BaseType, PDatum> =
    | Selection<GElement, Datum, PElement, PDatum>
    | Transition<GElement, Datum, PElement, PDatum>;

/**
 * Returns a new transition with the specified name. If a name is not specified, null is used.
 * The new transition is only exclusive with other transitions of the same name.
 *
 * The generic "OldDatum" refers to the type of a previously-set datum of the selected element in the Transition.
 *
 * @param name Name of the transition.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function transition<OldDatum>(name?: string): Transition<BaseType, OldDatum, null, undefined>;

/**
 * Returns a new transition from an existing transition.
 *
 * When using a transition instance, the returned transition has the same id and name as the specified transition.
 *
 * The generic "OldDatum" refers to the type of a previously-set datum of the selected element in the Transition.
 *
 * @param transition A transition instance.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function transition<OldDatum>(
    transition: Transition<BaseType, any, BaseType, any>,
): Transition<BaseType, OldDatum, null, undefined>;
