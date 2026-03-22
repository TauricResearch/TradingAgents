import type { Mutate, StateCreator, StoreApi, StoreMutatorIdentifier } from './vanilla.mjs';
type ExtractState<S> = S extends {
    getState: () => infer T;
} ? T : never;
type ReadonlyStoreApi<T> = Pick<StoreApi<T>, 'getState' | 'getInitialState' | 'subscribe'>;
type WithReact<S extends ReadonlyStoreApi<unknown>> = S & {
    /** @deprecated please use api.getInitialState() */
    getServerState?: () => ExtractState<S>;
};
export declare function useStoreWithEqualityFn<S extends WithReact<ReadonlyStoreApi<unknown>>>(api: S): ExtractState<S>;
export declare function useStoreWithEqualityFn<S extends WithReact<ReadonlyStoreApi<unknown>>, U>(api: S, selector: (state: ExtractState<S>) => U, equalityFn?: (a: U, b: U) => boolean): U;
export type UseBoundStoreWithEqualityFn<S extends WithReact<ReadonlyStoreApi<unknown>>> = {
    (): ExtractState<S>;
    <U>(selector: (state: ExtractState<S>) => U, equalityFn?: (a: U, b: U) => boolean): U;
} & S;
type CreateWithEqualityFn = {
    <T, Mos extends [StoreMutatorIdentifier, unknown][] = []>(initializer: StateCreator<T, [], Mos>, defaultEqualityFn?: <U>(a: U, b: U) => boolean): UseBoundStoreWithEqualityFn<Mutate<StoreApi<T>, Mos>>;
    <T>(): <Mos extends [StoreMutatorIdentifier, unknown][] = []>(initializer: StateCreator<T, [], Mos>, defaultEqualityFn?: <U>(a: U, b: U) => boolean) => UseBoundStoreWithEqualityFn<Mutate<StoreApi<T>, Mos>>;
};
export declare const createWithEqualityFn: CreateWithEqualityFn;
export {};
