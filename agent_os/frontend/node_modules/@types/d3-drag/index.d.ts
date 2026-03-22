// Last module patch version validated against: 3.0.0

import { Selection, ValueFn } from "d3-selection";

// --------------------------------------------------------------------------
// Shared Type Definitions and Interfaces
// --------------------------------------------------------------------------

/**
 * DraggedElementBaseType serves as an alias for the 'minimal' data type which can be selected
 * without 'd3-drag' (and related code in 'd3-selection') trying to use properties internally which would otherwise not
 * be supported.
 */
export type DraggedElementBaseType = Element;

/**
 * Container element type usable for mouse/touch functions
 */
export type DragContainerElement = HTMLElement | SVGSVGElement | SVGGElement; // HTMLElement includes HTMLCanvasElement

/**
 * The subject datum should at a minimum expose x and y properties, so that the relative position
 * of the subject and the pointer can be preserved during the drag gesture.
 */
export interface SubjectPosition {
    /**
     * x-coordinate
     */
    x: number;
    /**
     * y-coordinate
     */
    y: number;
}

/**
 * A D3 Drag Behavior
 *
 * The first generic refers to the type of element to be dragged.
 * The second generic refers to the type of the datum of the dragged element.
 * The third generic refers to the type of the drag behavior subject.
 *
 * The subject of a drag gesture represents the thing being dragged.
 * It is computed when an initiating input event is received,
 * such as a mousedown or touchstart, immediately before the drag gesture starts.
 * The subject is then exposed as event.subject on subsequent drag events for this gesture.
 *
 * The default subject is the datum of the element in the originating selection (see drag)
 * that received the initiating input event; if this datum is undefined,
 * an object representing the coordinates of the pointer is created.
 * When dragging circle elements in SVG, the default subject is thus the datum of the circle being dragged.
 * With Canvas, the default subject is the canvas element’s datum (regardless of where on the canvas you click).
 * In this case, a custom subject accessor would be more appropriate,
 * such as one that picks the closest circle to the mouse within a given search radius.
 */
export interface DragBehavior<GElement extends DraggedElementBaseType, Datum, Subject> extends Function {
    /**
     * Applies the drag behavior to the selected elements.
     * This function is typically not invoked directly, and is instead invoked via selection.call.
     *
     * For details see: {@link https://github.com/d3/d3-drag#_drag}
     *
     * @param selection A D3 selection of elements.
     * @param args Optional arguments to be passed in.
     */
    (selection: Selection<GElement, Datum, any, any>, ...args: any[]): void;

    /**
     * Returns the current container accessor function.
     */
    container(): ValueFn<GElement, Datum, DragContainerElement>;
    /**
     * Sets the container accessor to the specified function and returns the drag behavior.
     *
     * The container of a drag gesture determines the coordinate system of subsequent drag events, affecting event.x and event.y.
     * The element returned by the container accessor is subsequently passed to d3.pointer to determine the local coordinates of the pointer.
     *
     * The default container accessor returns the parent node of the element in the originating selection (see drag)
     * that received the initiating input event. This is often appropriate when dragging SVG or HTML elements,
     * since those elements are typically positioned relative to a parent. For dragging graphical elements with a Canvas,
     * however, you may want to redefine the container as the initiating element itself, using "this" in the accessor
     * function.
     *
     * @param accessor A container accessor function which is evaluated for each selected element,
     * in order, being passed the current datum (d), the current index (i), and the current group (nodes),
     * with this as the current DOM element. The function returns the container element.
     */
    container(accessor: ValueFn<GElement, Datum, DragContainerElement>): this;
    /**
     * Sets the container accessor to the specified object and returns the drag behavior.
     *
     * The container of a drag gesture determines the coordinate system of subsequent drag events, affecting event.x and event.y.
     * The element returned by the container accessor is subsequently passed to d3.pointer to determine the local coordinates of the pointer.
     *
     * The default container accessor returns the parent node of the element in the originating selection (see drag)
     * that received the initiating input event. This is often appropriate when dragging SVG or HTML elements,
     * since those elements are typically positioned relative to a parent. For dragging graphical elements with a Canvas,
     * however, you may want to redefine the container as the initiating element itself, such as drag.container(canvas).
     *
     * @param container Container element for the drag gesture.
     */
    container(container: DragContainerElement): this;

    /**
     * Returns the current filter function.
     */
    filter(): (this: GElement, event: any, d: Datum) => boolean;
    /**
     * Sets the event filter to the specified filter function and returns the drag behavior.
     *
     * If the filter returns falsey, the initiating event is ignored and no drag gesture is started.
     * Thus, the filter determines which input events are ignored. The default filter ignores mousedown events on secondary buttons,
     * since those buttons are typically intended for other purposes, such as the context menu.
     *
     * @param filterFn A filter function which is evaluated for each selected element,
     * in order, being passed the current event (event) and datum d, with the this context as the current DOM element.
     * The function returns a boolean value.
     */
    filter(filterFn: (this: GElement, event: any, d: Datum) => boolean): this;

    /**
     * Returns the current touch support detector, which defaults to a function returning true,
     * if the "ontouchstart" event is supported on the current element.
     */
    touchable(): ValueFn<GElement, Datum, boolean>;
    /**
     * Sets the touch support detector to the specified boolean value and returns the drag behavior.
     *
     * Touch event listeners are only registered if the detector returns truthy for the corresponding element when the drag behavior is applied.
     * The default detector works well for most browsers that are capable of touch input, but not all; Chrome’s mobile device emulator, for example,
     * fails detection.
     *
     * @param touchable A boolean value. true when touch event listeners should be applied to the corresponding element, otherwise false.
     */
    touchable(touchable: boolean): this;
    /**
     * Sets the touch support detector to the specified function and returns the drag behavior.
     *
     * Touch event listeners are only registered if the detector returns truthy for the corresponding element when the drag behavior is applied.
     * The default detector works well for most browsers that are capable of touch input, but not all; Chrome’s mobile device emulator, for example,
     * fails detection.
     *
     * @param touchable A touch support detector function, which returns true when touch event listeners should be applied to the corresponding element.
     * The function is evaluated for each selected element to which the drag behavior was applied, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element. The function returns a boolean value.
     */
    touchable(touchable: ValueFn<GElement, Datum, boolean>): this;

    /**
     *  Returns the current subject accessor functions.
     */
    subject(): (this: GElement, event: any, d: Datum) => Subject;
    /**
     * Sets the subject accessor to the specified function and returns the drag behavior.
     *
     * The subject of a drag gesture represents the thing being dragged.
     * It is computed when an initiating input event is received,
     * such as a mousedown or touchstart, immediately before the drag gesture starts.
     * The subject is then exposed as event.subject on subsequent drag events for this gesture.
     *
     * The default subject is the datum of the element in the originating selection (see drag)
     * that received the initiating input event; if this datum is undefined,
     * an object representing the coordinates of the pointer is created.
     * When dragging circle elements in SVG, the default subject is thus the datum of the circle being dragged.
     * With Canvas, the default subject is the canvas element’s datum (regardless of where on the canvas you click).
     * In this case, a custom subject accessor would be more appropriate,
     * such as one that picks the closest circle to the mouse within a given search radius.
     *
     * The subject of a drag gesture may not be changed after the gesture starts.
     *
     * During the evaluation of the subject accessor, event is a beforestart drag event.
     * Use event.sourceEvent to access the initiating input event and event.identifier to access the touch identifier.
     * The event.x and event.y are relative to the container, and are computed using d3.pointer.
     *
     * @param accessor An extent accessor function which is evaluated for each selected element,
     * in order, being passed the current event (`event`) and datum `d`, with the `this` context as the current DOM element.
     * The returned subject should be an object that exposes x and y properties,
     * so that the relative position of the subject and the pointer can be preserved during the drag gesture.
     * If the subject is null or undefined, no drag gesture is started for this pointer;
     * however, other starting touches may yet start drag gestures.
     */
    subject(accessor: (this: GElement, event: any, d: Datum) => Subject): this;

    /**
     * Return the current click distance threshold, which defaults to zero.
     */
    clickDistance(): number;
    /**
     * Set the maximum distance that the mouse can move between mousedown and mouseup that will trigger
     * a subsequent click event. If at any point between mousedown and mouseup the mouse is greater than or equal to
     * distance from its position on mousedown, the click event following mouseup will be suppressed.
     *
     * @param distance The distance threshold between mousedown and mouseup measured in client coordinates (event.clientX and event.clientY).
     * The default is zero.
     */
    clickDistance(distance: number): this;

    /**
     * Return the first currently-assigned listener matching the specified typenames, if any.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "drag.foo"" and "drag.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (after a new pointer becomes active [on mousedown or touchstart]), drag (after an active pointer moves [on mousemove or touchmove], or
     * end (after an active pointer becomes inactive [on mouseup, touchend or touchcancel].)
     */
    on(typenames: string): ((this: GElement, event: any, d: Datum) => void) | undefined;
    /**
     * Remove the current event listeners for the specified typenames, if any, return the drag behavior.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "drag.foo"" and "drag.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (after a new pointer becomes active [on mousedown or touchstart]), drag (after an active pointer moves [on mousemove or touchmove], or
     * end (after an active pointer becomes inactive [on mouseup, touchend or touchcancel].)
     * @param listener Use null to remove the listener.
     */
    on(typenames: string, listener: null): this;
    /**
     * Set the event listener for the specified typenames and return the drag behavior.
     * If an event listener was already registered for the same type and name,
     * the existing listener is removed before the new listener is added.
     * When a specified event is dispatched, each listener will be invoked with the same context and arguments as selection.on listeners.
     *
     * Changes to registered listeners via drag.on during a drag gesture do not affect the current drag gesture.
     * Instead, you must use event.on, which also allows you to register temporary event listeners for the current drag gesture.
     * Separate events are dispatched for each active pointer during a drag gesture.
     * For example, if simultaneously dragging multiple subjects with multiple fingers, a start event is dispatched for each finger,
     * even if both fingers start touching simultaneously.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "drag.foo"" and "drag.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (after a new pointer becomes active [on mousedown or touchstart]), drag (after an active pointer moves [on mousemove or touchmove], or
     * end (after an active pointer becomes inactive [on mouseup, touchend or touchcancel].)
     * @param listener An event listener function which is evaluated for each selected element,
     * in order, being passed the current event (event) and datum d, with the this context as the current DOM element.
     */
    on(typenames: string, listener: (this: GElement, event: any, d: Datum) => void): this;
}

/**
 * Creates a new drag behavior. The returned behavior, drag, is both an object and a function, and is
 * typically applied to selected elements via selection.call.
 *
 * Use this signature when using the default subject accessor.
 *
 * The first generic refers to the type of element to be dragged.
 * The second generic refers to the type of the datum of the dragged element.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function drag<GElement extends DraggedElementBaseType, Datum>(): DragBehavior<
    GElement,
    Datum,
    Datum | SubjectPosition
>;
/**
 * Creates a new drag behavior. The returned behavior, drag, is both an object and a function, and is
 * typically applied to selected elements via selection.call.
 *
 * Use this signature when using a custom subject accessor.
 *
 * The first generic refers to the type of element to be dragged.
 * The second generic refers to the type of the datum of the dragged element.
 * The third generic refers to the type of the drag behavior subject.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function drag<GElement extends DraggedElementBaseType, Datum, Subject>(): DragBehavior<GElement, Datum, Subject>;

/**
 * D3 Drag event
 *
 * The first generic refers to the type of element to be dragged.
 * The second generic refers to the type of the datum of the dragged element.
 * The third generic refers to the type of the drag behavior subject.
 */
export interface D3DragEvent<GElement extends DraggedElementBaseType, Datum, Subject> {
    /**
     * The DragBehavior associated with the event
     */
    target: DragBehavior<GElement, Datum, Subject>;
    /**
     * The event type for the DragEvent
     */
    type: "start" | "drag" | "end" | string; // Leave failsafe string type for cases like 'drag.foo'
    /**
     * The drag subject, defined by drag.subject.
     */
    subject: Subject;
    /**
     * The new x-coordinate of the subject, relative to the container
     */
    x: number;
    /**
     * The new y-coordinate of the subject, relative to the container
     */
    y: number;
    /**
     * The change in x-coordinate since the previous drag event.
     */
    dx: number;
    /**
     * The change in y-coordinate since the previous drag event.
     */
    dy: number;
    /**
     * The string “mouse”, or a numeric touch identifier.
     */
    identifier: "mouse" | number;
    /**
     * The number of currently active drag gestures (on start and end, not including this one).
     *
     * The event.active field is useful for detecting the first start event and the last end event
     * in a sequence of concurrent drag gestures: it is zero when the first drag gesture starts,
     * and zero when the last drag gesture ends.
     */
    active: number;
    /**
     * The underlying input event, such as mousemove or touchmove.
     */
    sourceEvent: any;
    /**
     * Return the first currently-assigned listener matching the specified typenames, if any.
     *
     * Equivalent to drag.on, but only applies to the current drag gesture. Before the drag gesture starts,
     * a copy of the current drag event listeners is made. This copy is bound to the current drag gesture
     * and modified by event.on. This is useful for temporary listeners that only receive events for the current drag gesture.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "drag.foo"" and "drag.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (after a new pointer becomes active [on mousedown or touchstart]), drag (after an active pointer moves [on mousemove or touchmove], or
     * end (after an active pointer becomes inactive [on mouseup, touchend or touchcancel].)
     */
    on(typenames: string): ((this: GElement, event: any, d: Datum) => void) | undefined;
    /**
     * Remove the current event listeners for the specified typenames, if any, return the drag behavior.
     *
     * Equivalent to drag.on, but only applies to the current drag gesture. Before the drag gesture starts,
     * a copy of the current drag event listeners is made. This copy is bound to the current drag gesture
     * and modified by event.on. This is useful for temporary listeners that only receive events for the current drag gesture.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "drag.foo"" and "drag.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (after a new pointer becomes active [on mousedown or touchstart]), drag (after an active pointer moves [on mousemove or touchmove], or
     * end (after an active pointer becomes inactive [on mouseup, touchend or touchcancel].)
     * @param listener Use null to remove the listener.
     */
    on(typenames: string, listener: null): this;
    /**
     * Set the event listener for the specified typenames and return the drag behavior.
     * If an event listener was already registered for the same type and name,
     * the existing listener is removed before the new listener is added.
     * When a specified event is dispatched, each listener will be invoked with the same context and arguments as selection.on listeners.
     *
     * Equivalent to drag.on, but only applies to the current drag gesture. Before the drag gesture starts,
     * a copy of the current drag event listeners is made. This copy is bound to the current drag gesture
     * and modified by event.on. This is useful for temporary listeners that only receive events for the current drag gesture.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "drag.foo"" and "drag.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (after a new pointer becomes active [on mousedown or touchstart]), drag (after an active pointer moves [on mousemove or touchmove], or
     * end (after an active pointer becomes inactive [on mouseup, touchend or touchcancel].)
     * @param listener An event listener function which is evaluated for each selected element,
     * in order, being passed the current event (event) and datum d, with the this context as the current DOM element.
     */
    on(typenames: string, listener: (this: GElement, event: any, d: Datum) => void): this;
}

/**
 * Prevents native drag-and-drop and text selection on the specified window.
 * As an alternative to preventing the default action of mousedown events,
 * this method prevents undesirable default actions following mousedown. In supported browsers,
 * this means capturing dragstart and selectstart events, preventing the associated default actions,
 * and immediately stopping their propagation. In browsers that do not support selection events,
 * the user-select CSS property is set to none on the document element.
 * This method is intended to be called on mousedown, followed by d3.dragEnable on mouseup.
 *
 * @param window The window for which drag should be disabled.
 */
export function dragDisable(window: Window): void;

/**
 * Allows native drag-and-drop and text selection on the specified window; undoes the effect of d3.dragDisable.
 * This method is intended to be called on mouseup, preceded by d3.dragDisable on mousedown.
 * If noclick is true, this method also temporarily suppresses click events.
 * The suppression of click events expires after a zero-millisecond timeout,
 * such that it only suppress the click event that would immediately follow the current mouseup event, if any.
 *
 * @param window The window for which drag should be (re-)enabled.
 * @param noClick An optional flag. If noclick is true, this method also temporarily suppresses click events.
 */
export function dragEnable(window: Window, noClick?: boolean): void;
