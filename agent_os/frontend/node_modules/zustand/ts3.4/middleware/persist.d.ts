import { StateCreator, StoreMutatorIdentifier } from '../vanilla';
export interface StateStorage {
    getItem: (name: string) => string | null | Promise<string | null>;
    setItem: (name: string, value: string) => unknown | Promise<unknown>;
    removeItem: (name: string) => unknown | Promise<unknown>;
}
export type StorageValue<S> = {
    state: S;
    version?: number;
};
export interface PersistStorage<S> {
    getItem: (name: string) => StorageValue<S> | null | Promise<StorageValue<S> | null>;
    setItem: (name: string, value: StorageValue<S>) => unknown | Promise<unknown>;
    removeItem: (name: string) => unknown | Promise<unknown>;
}
type JsonStorageOptions = {
    reviver?: (key: string, value: unknown) => unknown;
    replacer?: (key: string, value: unknown) => unknown;
};
export declare function createJSONStorage<S>(getStorage: () => StateStorage, options?: JsonStorageOptions): PersistStorage<S> | undefined;
export interface PersistOptions<S, PersistedState = S> {
    /** Name of the storage (must be unique) */
    name: string;
    /**
     * @deprecated Use `storage` instead.
     * A function returning a storage.
     * The storage must fit `window.localStorage`'s api (or an async version of it).
     * For example the storage could be `AsyncStorage` from React Native.
     *
     * @default () => localStorage
     */
    getStorage?: () => StateStorage;
    /**
     * @deprecated Use `storage` instead.
     * Use a custom serializer.
     * The returned string will be stored in the storage.
     *
     * @default JSON.stringify
     */
    serialize?: (state: StorageValue<S>) => string | Promise<string>;
    /**
     * @deprecated Use `storage` instead.
     * Use a custom deserializer.
     * Must return an object matching StorageValue<S>
     *
     * @param str The storage's current value.
     * @default JSON.parse
     */
    deserialize?: (str: string) => StorageValue<PersistedState> | Promise<StorageValue<PersistedState>>;
    /**
     * Use a custom persist storage.
     *
     * Combining `createJSONStorage` helps creating a persist storage
     * with JSON.parse and JSON.stringify.
     *
     * @default createJSONStorage(() => localStorage)
     */
    storage?: PersistStorage<PersistedState> | undefined;
    /**
     * Filter the persisted value.
     *
     * @params state The state's value
     */
    partialize?: (state: S) => PersistedState;
    /**
     * A function returning another (optional) function.
     * The main function will be called before the state rehydration.
     * The returned function will be called after the state rehydration or when an error occurred.
     */
    onRehydrateStorage?: (state: S) => ((state?: S, error?: unknown) => void) | void;
    /**
     * If the stored state's version mismatch the one specified here, the storage will not be used.
     * This is useful when adding a breaking change to your store.
     */
    version?: number;
    /**
     * A function to perform persisted state migration.
     * This function will be called when persisted state versions mismatch with the one specified here.
     */
    migrate?: (persistedState: unknown, version: number) => PersistedState | Promise<PersistedState>;
    /**
     * A function to perform custom hydration merges when combining the stored state with the current one.
     * By default, this function does a shallow merge.
     */
    merge?: (persistedState: unknown, currentState: S) => S;
    /**
     * An optional boolean that will prevent the persist middleware from triggering hydration on initialization,
     * This allows you to call `rehydrate()` at a specific point in your apps rendering life-cycle.
     *
     * This is useful in SSR application.
     *
     * @default false
     */
    skipHydration?: boolean;
}
type PersistListener<S> = (state: S) => void;
type StorePersist<S, Ps> = {
    persist: {
        setOptions: (options: Partial<PersistOptions<S, Ps>>) => void;
        clearStorage: () => void;
        rehydrate: () => Promise<void> | void;
        hasHydrated: () => boolean;
        onHydrate: (fn: PersistListener<S>) => () => void;
        onFinishHydration: (fn: PersistListener<S>) => () => void;
        getOptions: () => Partial<PersistOptions<S, Ps>>;
    };
};
type Persist = <T, Mps extends [
    StoreMutatorIdentifier,
    unknown
][] = [
], Mcs extends [
    StoreMutatorIdentifier,
    unknown
][] = [
], U = T>(initializer: StateCreator<T, [
    ...Mps,
    [
        'zustand/persist',
        unknown
    ]
], Mcs>, options: PersistOptions<T, U>) => StateCreator<T, Mps, [
    [
        'zustand/persist',
        U
    ],
    ...Mcs
]>;
declare module '../vanilla' {
    interface StoreMutators<S, A> {
        'zustand/persist': WithPersist<S, A>;
    }
}
type Write<T, U> = Pick<T, Exclude<keyof T, keyof U>> & U;
type WithPersist<S, A> = S extends {
    getState: () => infer T;
} ? Write<S, StorePersist<T, A>> : never;
export declare const persist: Persist;
export {};
