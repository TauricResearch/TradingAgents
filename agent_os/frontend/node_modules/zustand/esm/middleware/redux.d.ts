import type { StateCreator, StoreMutatorIdentifier } from '../vanilla';
type Write<T, U> = Omit<T, keyof U> & U;
type Action = {
    type: string;
};
type StoreRedux<A> = {
    dispatch: (a: A) => A;
    dispatchFromDevtools: true;
};
type ReduxState<A> = {
    dispatch: StoreRedux<A>['dispatch'];
};
type WithRedux<S, A> = Write<S, StoreRedux<A>>;
type Redux = <T, A extends Action, Cms extends [StoreMutatorIdentifier, unknown][] = []>(reducer: (state: T, action: A) => T, initialState: T) => StateCreator<Write<T, ReduxState<A>>, Cms, [['zustand/redux', A]]>;
declare module '../vanilla' {
    interface StoreMutators<S, A> {
        'zustand/redux': WithRedux<S, A>;
    }
}
export declare const redux: Redux;
export {};
