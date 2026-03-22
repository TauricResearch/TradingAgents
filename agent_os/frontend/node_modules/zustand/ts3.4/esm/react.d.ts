import { Mutate, StateCreator, StoreApi, StoreMutatorIdentifier } from './vanilla';
type ExtractState<S> = S extends {
    getState: () => infer T;
} ? T : never;
type ReadonlyStoreApi<T> = Pick<StoreApi<T>, 'getState' | 'getInitialState' | 'subscribe'>;
type WithReact<S extends ReadonlyStoreApi<unknown>> = S & {
    /** @deprecated please use api.getInitialState() */
    getServerState?: () => ExtractState<S>;
};
export declare function useStore<S extends WithReact<ReadonlyStoreApi<unknown>>>(api: S): ExtractState<S>;
export declare function useStore<S extends WithReact<ReadonlyStoreApi<unknown>>, U>(api: S, selector: (state: ExtractState<S>) => U): U;
/**
 * @deprecated The usage with three arguments is deprecated. Use `useStoreWithEqualityFn` from 'zustand/traditional'. The usage with one or two arguments is not deprecated.
 * https://github.com/pmndrs/zustand/discussions/1937
 */
export declare function useStore<S extends WithReact<ReadonlyStoreApi<unknown>>, U>(api: S, selector: (state: ExtractState<S>) => U, equalityFn: ((a: U, b: U) => boolean) | undefined): U;
export type UseBoundStore<S extends WithReact<ReadonlyStoreApi<unknown>>> = {
    (): ExtractState<S>;
    <U>(selector: (state: ExtractState<S>) => U): U;
    /**
     * @deprecated Use `createWithEqualityFn` from 'zustand/traditional'
     */
    <U>(selector: (state: ExtractState<S>) => U, equalityFn: (a: U, b: U) => boolean): U;
} & S;
type Create = {
    <T, Mos extends [
        StoreMutatorIdentifier,
        unknown
    ][] = [
    ]>(initializer: StateCreator<T, [
    ], Mos>): UseBoundStore<Mutate<StoreApi<T>, Mos>>;
    <T>(): <Mos extends [
        StoreMutatorIdentifier,
        unknown
    ][] = [
    ]>(initializer: StateCreator<T, [
    ], Mos>) => UseBoundStore<Mutate<StoreApi<T>, Mos>>;
    /**
     * @deprecated Use `useStore` hook to bind store
     */
    <S extends StoreApi<unknown>>(store: S): UseBoundStore<S>;
};
export declare const create: Create;
/**
 * @deprecated Use `import { create } from 'zustand'`
 */
declare const _default: Create;
export default _default;
