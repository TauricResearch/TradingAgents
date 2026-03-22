import { Draft } from 'immer';
import { StateCreator, StoreMutatorIdentifier } from '../vanilla';
type Immer = <T, Mps extends [
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
        'zustand/immer',
        never
    ]
], Mcs>) => StateCreator<T, Mps, [
    [
        'zustand/immer',
        never
    ],
    ...Mcs
]>;
declare module '../vanilla' {
    interface StoreMutators<S, A> {
        ['zustand/immer']: WithImmer<S>;
    }
}
type Write<T, U> = Pick<T, Exclude<keyof T, keyof U>> & U;
type SkipTwo<T> = T extends {
    length: 0;
} ? [
] : T extends {
    length: 1;
} ? [
] : T extends {
    length: 0 | 1;
} ? [
] : T extends [
    unknown,
    unknown,
    ...infer A
] ? A : T extends [
    unknown,
    unknown?,
    ...infer A
] ? A : T extends [
    unknown?,
    unknown?,
    ...infer A
] ? A : never;
type WithImmer<S> = Write<S, StoreImmer<S>>;
type StoreImmer<S> = S extends {
    getState: () => infer T;
    setState: infer SetState;
} ? SetState extends (...a: infer A) => infer Sr ? {
    setState(nextStateOrUpdater: T | Partial<T> | ((state: Draft<T>) => void), shouldReplace?: boolean | undefined, ...a: SkipTwo<A>): Sr;
} : never : never;
export declare const immer: Immer;
export {};
