import * as React from 'react'
import Emotion, { createEmotionProps } from './emotion-element'
import { EmotionJSX } from './jsx-namespace'
import { hasOwn } from './utils'

export const jsx: typeof React.createElement = function (
  type: any,
  props: any
): any {
  // eslint-disable-next-line prefer-rest-params
  let args: any = arguments

  if (props == null || !hasOwn.call(props, 'css')) {
    return React.createElement.apply(undefined, args)
  }

  let argsLength = args.length
  let createElementArgArray: any = new Array(argsLength)
  createElementArgArray[0] = Emotion
  createElementArgArray[1] = createEmotionProps(type, props)

  for (let i = 2; i < argsLength; i++) {
    createElementArgArray[i] = args[i]
  }

  return React.createElement.apply(null, createElementArgArray)
}
export namespace jsx {
  export namespace JSX {
    export type ElementType = EmotionJSX.ElementType
    export interface Element extends EmotionJSX.Element {}
    export interface ElementClass extends EmotionJSX.ElementClass {}
    export interface ElementAttributesProperty
      extends EmotionJSX.ElementAttributesProperty {}
    export interface ElementChildrenAttribute
      extends EmotionJSX.ElementChildrenAttribute {}
    export type LibraryManagedAttributes<C, P> =
      EmotionJSX.LibraryManagedAttributes<C, P>
    export interface IntrinsicAttributes
      extends EmotionJSX.IntrinsicAttributes {}
    export interface IntrinsicClassAttributes<T>
      extends EmotionJSX.IntrinsicClassAttributes<T> {}
    export type IntrinsicElements = EmotionJSX.IntrinsicElements
  }
}
