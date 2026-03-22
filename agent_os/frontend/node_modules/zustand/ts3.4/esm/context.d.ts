import ReactExports from 'react';
import { ReactNode } from 'react';
import { StoreApi } from 'zustand';
type UseContextStore<S extends StoreApi<unknown>> = {
    (): ExtractState<S>;
    <U>(selector: (state: ExtractState<S>) => U, equalityFn?: (a: U, b: U) => boolean): U;
};
type ExtractState<S> = S extends {
    getState: () => infer T;
} ? T : never;
type WithoutCallSignature<T> = {
    [K in keyof T]: T[K];
};
/**
 * @deprecated Use `createStore` and `useStore` for context usage
 */
declare function createContext<S extends StoreApi<unknown>>(): {
    Provider: ({ createStore, children, }: {
        createStore: () => S;
        children: ReactNode;
    }) => ReactExports.FunctionComponentElement<ReactExports.ProviderProps<S | undefined>>;
    useStore: UseContextStore<S>;
    useStoreApi: () => WithoutCallSignature<S>;
};
export default createContext;
