type SetStateInternal<T> = {
    _(partial: T | Partial<T> | {
        _(state: T): T | Partial<T>;
    }['_'], replace?: boolean | undefined): void;
}['_'];
export interface StoreApi<T> {
    setState: SetStateInternal<T>;
    getState: () => T;
    getInitialState: () => T;
    subscribe: (listener: (state: T, prevState: T) => void) => () => void;
    /**
     * @deprecated Use `unsubscribe` returned by `subscribe`
     */
    destroy: () => void;
}
type Get<T, K, F> = K extends keyof T ? T[K] : F;
export type Mutate<S, Ms> = number extends Ms['length' & keyof Ms] ? S : Ms extends [
] ? S : Ms extends [
    [
        infer Mi,
        infer Ma
    ],
    ...infer Mrs
] ? Mutate<StoreMutators<S, Ma>[Mi & StoreMutatorIdentifier], Mrs> : never;
export type StateCreator<T, Mis extends [
    StoreMutatorIdentifier,
    unknown
][] = [
], Mos extends [
    StoreMutatorIdentifier,
    unknown
][] = [
], U = T> = ((setState: Get<Mutate<StoreApi<T>, Mis>, 'setState', never>, getState: Get<Mutate<StoreApi<T>, Mis>, 'getState', never>, store: Mutate<StoreApi<T>, Mis>) => U) & {
    $$storeMutators?: Mos;
};
export interface StoreMutators<S, A> {
}
export type StoreMutatorIdentifier = keyof StoreMutators<unknown, unknown>;
type CreateStore = {
    <T, Mos extends [
        StoreMutatorIdentifier,
        unknown
    ][] = [
    ]>(initializer: StateCreator<T, [
    ], Mos>): Mutate<StoreApi<T>, Mos>;
    <T>(): <Mos extends [
        StoreMutatorIdentifier,
        unknown
    ][] = [
    ]>(initializer: StateCreator<T, [
    ], Mos>) => Mutate<StoreApi<T>, Mos>;
};
export declare const createStore: CreateStore;
/**
 * @deprecated Use `import { createStore } from 'zustand/vanilla'`
 */
declare const _default: CreateStore;
export default _default;
/**
 * @deprecated Use `unknown` instead of `State`
 */
export type State = unknown;
/**
 * @deprecated Use `Partial<T> | ((s: T) => Partial<T>)` instead of `PartialState<T>`
 */
export type PartialState<T extends State> = Partial<T> | ((state: T) => Partial<T>);
/**
 * @deprecated Use `(s: T) => U` instead of `StateSelector<T, U>`
 */
export type StateSelector<T extends State, U> = (state: T) => U;
/**
 * @deprecated Use `(a: T, b: T) => boolean` instead of `EqualityChecker<T>`
 */
export type EqualityChecker<T> = (state: T, newState: T) => boolean;
/**
 * @deprecated Use `(state: T, previousState: T) => void` instead of `StateListener<T>`
 */
export type StateListener<T> = (state: T, previousState: T) => void;
/**
 * @deprecated Use `(slice: T, previousSlice: T) => void` instead of `StateSliceListener<T>`.
 */
export type StateSliceListener<T> = (slice: T, previousSlice: T) => void;
/**
 * @deprecated Use `(listener: (state: T) => void) => void` instead of `Subscribe<T>`.
 */
export type Subscribe<T extends State> = {
    (listener: (state: T, previousState: T) => void): () => void;
};
/**
 * @deprecated You might be looking for `StateCreator`, if not then
 * use `StoreApi<T>['setState']` instead of `SetState<T>`.
 */
export type SetState<T extends State> = {
    _(partial: T | Partial<T> | {
        _(state: T): T | Partial<T>;
    }['_'], replace?: boolean | undefined): void;
}['_'];
/**
 * @deprecated You might be looking for `StateCreator`, if not then
 * use `StoreApi<T>['getState']` instead of `GetState<T>`.
 */
export type GetState<T extends State> = () => T;
/**
 * @deprecated Use `StoreApi<T>['destroy']` instead of `Destroy`.
 */
export type Destroy = () => void;
