import type { StateCreator, StoreApi, StoreMutatorIdentifier } from '../vanilla';
type Config = Parameters<(Window extends {
    __REDUX_DEVTOOLS_EXTENSION__?: infer T;
} ? T : {
    connect: (param: any) => any;
})['connect']>[0];
declare module '../vanilla' {
    interface StoreMutators<S, A> {
        'zustand/devtools': WithDevtools<S>;
    }
}
type Cast<T, U> = T extends U ? T : U;
type Write<T, U> = Omit<T, keyof U> & U;
type TakeTwo<T> = T extends {
    length: 0;
} ? [undefined, undefined] : T extends {
    length: 1;
} ? [...a0: Cast<T, unknown[]>, a1: undefined] : T extends {
    length: 0 | 1;
} ? [...a0: Cast<T, unknown[]>, a1: undefined] : T extends {
    length: 2;
} ? T : T extends {
    length: 1 | 2;
} ? T : T extends {
    length: 0 | 1 | 2;
} ? T : T extends [infer A0, infer A1, ...unknown[]] ? [A0, A1] : T extends [infer A0, (infer A1)?, ...unknown[]] ? [A0, A1?] : T extends [(infer A0)?, (infer A1)?, ...unknown[]] ? [A0?, A1?] : never;
type WithDevtools<S> = Write<S, StoreDevtools<S>>;
type StoreDevtools<S> = S extends {
    setState: (...a: infer Sa) => infer Sr;
} ? {
    setState<A extends string | {
        type: string;
    }>(...a: [...a: TakeTwo<Sa>, action?: A]): Sr;
} : never;
export interface DevtoolsOptions extends Config {
    name?: string;
    enabled?: boolean;
    anonymousActionType?: string;
    store?: string;
}
type Devtools = <T, Mps extends [StoreMutatorIdentifier, unknown][] = [], Mcs extends [StoreMutatorIdentifier, unknown][] = []>(initializer: StateCreator<T, [...Mps, ['zustand/devtools', never]], Mcs>, devtoolsOptions?: DevtoolsOptions) => StateCreator<T, Mps, [['zustand/devtools', never], ...Mcs]>;
declare module '../vanilla' {
    interface StoreMutators<S, A> {
        'zustand/devtools': WithDevtools<S>;
    }
}
export type NamedSet<T> = WithDevtools<StoreApi<T>>['setState'];
export declare const devtools: Devtools;
export {};
