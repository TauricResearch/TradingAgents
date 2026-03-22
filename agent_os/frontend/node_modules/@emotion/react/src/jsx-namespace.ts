import 'react'
import { Interpolation } from '@emotion/serialize'
import { Theme } from './theming'

type IsPreReact19 = 2 extends Parameters<React.FunctionComponent<any>>['length']
  ? true
  : false

type WithConditionalCSSProp<P> = 'className' extends keyof P
  ? string extends P['className' & keyof P]
    ? { css?: Interpolation<Theme> }
    : {}
  : {}

// unpack all here to avoid infinite self-referencing when defining our own JSX namespace for the pre-React 19 case

// the IsPreReact19 and @ts-ignore comments are to allow @emotion/react to support three different cases of types
// - pre-React 18.something which didn't have `React.JSX`
// - React 18.something with `React.JSX`
// - React 19 with `React.JSX` and no global `JSX`
// we support both pre-React 19 cases by using the global `JSX` and with the React 19 types, we use `React.JSX`
// to make this work, we need @ts-ignore comments to ignore references that are invalid
// though note that the error types resulting from ignoring the errors will never be used
// since the pre vs post React 19 conditional will pick the one that won't error

// prettier-ignore
/** @ts-ignore */
type ReactJSXElement = true extends IsPreReact19 ? JSX.Element : React.JSX.Element

// prettier-ignore
/** @ts-ignore */
type ReactJSXElementClass = true extends IsPreReact19 ? JSX.ElementClass : React.JSX.ElementClass

// prettier-ignore
/** @ts-ignore */
type ReactJSXElementAttributesProperty = true extends IsPreReact19 ? JSX.ElementAttributesProperty : React.JSX.ElementAttributesProperty

// prettier-ignore
/** @ts-ignore */
type ReactJSXElementChildrenAttribute = true extends IsPreReact19 ? JSX.ElementChildrenAttribute : React.JSX.ElementChildrenAttribute

// prettier-ignore
/** @ts-ignore */
type ReactJSXLibraryManagedAttributes<C, P> = true extends IsPreReact19 ? JSX.LibraryManagedAttributes<C, P> : React.JSX.LibraryManagedAttributes<C, P>

// prettier-ignore
/** @ts-ignore */
type ReactJSXIntrinsicAttributes = true extends IsPreReact19 ? JSX.IntrinsicAttributes : React.JSX.IntrinsicAttributes

// prettier-ignore
/** @ts-ignore */
type ReactJSXIntrinsicClassAttributes<T> = true extends IsPreReact19 ? JSX.IntrinsicClassAttributes<T> : React.JSX.IntrinsicClassAttributes<T>

// prettier-ignore
/** @ts-ignore */
type ReactJSXIntrinsicElements = true extends IsPreReact19 ? JSX.IntrinsicElements : React.JSX.IntrinsicElements

// based on the code from @types/react@18.2.8
// https://github.com/DefinitelyTyped/DefinitelyTyped/blob/3197efc097d522c4bf02b94e1a0766d007d6cdeb/types/react/index.d.ts#LL3204C13-L3204C13
// prettier-ignore
/** @ts-ignore */
type ReactJSXElementType = true extends IsPreReact19 ? string | React.JSXElementConstructor<any> : React.JSX.ElementType

export namespace ReactJSX {
  export type ElementType = ReactJSXElementType
  export interface Element extends ReactJSXElement {}
  export interface ElementClass extends ReactJSXElementClass {}
  export interface ElementAttributesProperty
    extends ReactJSXElementAttributesProperty {}
  export interface ElementChildrenAttribute
    extends ReactJSXElementChildrenAttribute {}

  export type LibraryManagedAttributes<C, P> = ReactJSXLibraryManagedAttributes<
    C,
    P
  >

  export interface IntrinsicAttributes extends ReactJSXIntrinsicAttributes {}
  export interface IntrinsicClassAttributes<T>
    extends ReactJSXIntrinsicClassAttributes<T> {}

  export type IntrinsicElements = ReactJSXIntrinsicElements
}

export namespace EmotionJSX {
  export type ElementType = ReactJSXElementType
  export interface Element extends ReactJSXElement {}
  export interface ElementClass extends ReactJSXElementClass {}
  export interface ElementAttributesProperty
    extends ReactJSXElementAttributesProperty {}
  export interface ElementChildrenAttribute
    extends ReactJSXElementChildrenAttribute {}

  export type LibraryManagedAttributes<C, P> = P extends unknown
    ? WithConditionalCSSProp<P> & ReactJSXLibraryManagedAttributes<C, P>
    : never

  export interface IntrinsicAttributes extends ReactJSXIntrinsicAttributes {}
  export interface IntrinsicClassAttributes<T>
    extends ReactJSXIntrinsicClassAttributes<T> {}

  export type IntrinsicElements = {
    [K in keyof ReactJSXIntrinsicElements]: ReactJSXIntrinsicElements[K] & {
      css?: Interpolation<Theme>
    }
  }
}
