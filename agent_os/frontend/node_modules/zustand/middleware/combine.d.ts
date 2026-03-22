import type { StateCreator, StoreMutatorIdentifier } from '../vanilla';
type Write<T, U> = Omit<T, keyof U> & U;
type Combine = <T extends object, U extends object, Mps extends [StoreMutatorIdentifier, unknown][] = [], Mcs extends [StoreMutatorIdentifier, unknown][] = []>(initialState: T, additionalStateCreator: StateCreator<T, Mps, Mcs, U>) => StateCreator<Write<T, U>, Mps, Mcs>;
export declare const combine: Combine;
export {};
