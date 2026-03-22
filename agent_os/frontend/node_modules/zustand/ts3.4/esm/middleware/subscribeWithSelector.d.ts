import { StateCreator, StoreMutatorIdentifier } from '../vanilla';
type SubscribeWithSelector = <T, Mps extends [
    StoreMutatorIdentifier,
    unknown
][] = [
], Mcs extends [
    StoreMutatorIdentifier,
    unknown
][] = [
]>(initializer: StateCreator<T, [
    ...Mps,
    [
        'zustand/subscribeWithSelector',
        never
    ]
], Mcs>) => StateCreator<T, Mps, [
    [
        'zustand/subscribeWithSelector',
        never
    ],
    ...Mcs
]>;
type Write<T, U> = Pick<T, Exclude<keyof T, keyof U>> & U;
type WithSelectorSubscribe<S> = S extends {
    getState: () => infer T;
} ? Write<S, StoreSubscribeWithSelector<T>> : never;
declare module '../vanilla' {
    interface StoreMutators<S, A> {
        ['zustand/subscribeWithSelector']: WithSelectorSubscribe<S>;
    }
}
type StoreSubscribeWithSelector<T> = {
    subscribe: {
        (listener: (selectedState: T, previousSelectedState: T) => void): () => void;
        <U>(selector: (state: T) => U, listener: (selectedState: U, previousSelectedState: U) => void, options?: {
            equalityFn?: (a: U, b: U) => boolean;
            fireImmediately?: boolean;
        }): () => void;
    };
};
export declare const subscribeWithSelector: SubscribeWithSelector;
export {};
