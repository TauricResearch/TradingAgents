import { ComponentSelector, Interpolation } from '@emotion/serialize'
import { ReactJSXIntrinsicElements } from './jsx-namespace'
import { PropsOf, Theme } from '@emotion/react'

/** Same as StyledOptions but shouldForwardProp must be a type guard */
export interface FilteringStyledOptions<
  Props = Record<string, any>,
  ForwardedProps extends keyof Props & string = keyof Props & string
> {
  label?: string
  shouldForwardProp?: (propName: string) => propName is ForwardedProps
  target?: string
}

export interface StyledOptions<Props = Record<string, any>> {
  label?: string
  shouldForwardProp?: (propName: string) => boolean
  target?: string
}

/**
 * @typeparam ComponentProps  Props which will be included when withComponent is called
 * @typeparam SpecificComponentProps  Props which will *not* be included when withComponent is called
 */
export interface StyledComponent<
  ComponentProps extends {},
  SpecificComponentProps extends {} = {},
  JSXProps extends {} = {}
> extends React.FC<ComponentProps & SpecificComponentProps & JSXProps>,
    ComponentSelector {
  withComponent<C extends React.ComponentClass<React.ComponentProps<C>>>(
    component: C
  ): StyledComponent<
    ComponentProps & PropsOf<C>,
    {},
    { ref?: React.Ref<InstanceType<C>> }
  >
  withComponent<C extends React.ComponentType<React.ComponentProps<C>>>(
    component: C
  ): StyledComponent<ComponentProps & PropsOf<C>>
  withComponent<Tag extends keyof ReactJSXIntrinsicElements>(
    tag: Tag
  ): StyledComponent<ComponentProps, ReactJSXIntrinsicElements[Tag]>
}

/**
 * @typeparam ComponentProps  Props which will be included when withComponent is called
 * @typeparam SpecificComponentProps  Props which will *not* be included when withComponent is called
 */
export interface CreateStyledComponent<
  ComponentProps extends {},
  SpecificComponentProps extends {} = {},
  JSXProps extends {} = {}
> {
  (
    template: TemplateStringsArray,
    ...styles: Array<
      Interpolation<ComponentProps & SpecificComponentProps & { theme: Theme }>
    >
  ): StyledComponent<ComponentProps, SpecificComponentProps, JSXProps>

  /**
   * @typeparam AdditionalProps  Additional props to add to your styled component
   */
  <AdditionalProps extends {}>(
    template: TemplateStringsArray,
    ...styles: Array<
      Interpolation<
        ComponentProps &
          SpecificComponentProps &
          AdditionalProps & { theme: Theme }
      >
    >
  ): StyledComponent<
    ComponentProps & AdditionalProps,
    SpecificComponentProps,
    JSXProps
  >

  /**
   * @typeparam AdditionalProps  Additional props to add to your styled component
   */
  <AdditionalProps extends {} = {}>(
    ...styles: Array<
      Interpolation<
        ComponentProps &
          SpecificComponentProps &
          AdditionalProps & { theme: Theme }
      >
    >
  ): StyledComponent<
    ComponentProps & AdditionalProps,
    SpecificComponentProps,
    JSXProps
  >
}

/**
 * @desc
 * This function accepts a React component or tag ('div', 'a' etc).
 *
 * @example styled(MyComponent)({ width: 100 })
 * @example styled(MyComponent)(myComponentProps => ({ width: myComponentProps.width })
 * @example styled('div')({ width: 100 })
 * @example styled('div')<Props>(props => ({ width: props.width })
 */
export interface CreateStyled {
  <
    C extends React.ComponentClass<React.ComponentProps<C>>,
    ForwardedProps extends keyof React.ComponentProps<C> &
      string = keyof React.ComponentProps<C> & string
  >(
    component: C,
    options: FilteringStyledOptions<React.ComponentProps<C>, ForwardedProps>
  ): CreateStyledComponent<
    Pick<PropsOf<C>, ForwardedProps> & {
      theme?: Theme
    },
    {},
    {
      ref?: React.Ref<InstanceType<C>>
    }
  >

  <C extends React.ComponentClass<React.ComponentProps<C>>>(
    component: C,
    options?: StyledOptions<React.ComponentProps<C>>
  ): CreateStyledComponent<
    PropsOf<C> & {
      theme?: Theme
    },
    {},
    {
      ref?: React.Ref<InstanceType<C>>
    }
  >

  <
    C extends React.ComponentType<React.ComponentProps<C>>,
    ForwardedProps extends keyof React.ComponentProps<C> &
      string = keyof React.ComponentProps<C> & string
  >(
    component: C,
    options: FilteringStyledOptions<React.ComponentProps<C>, ForwardedProps>
  ): CreateStyledComponent<
    Pick<PropsOf<C>, ForwardedProps> & {
      theme?: Theme
    }
  >

  <C extends React.ComponentType<React.ComponentProps<C>>>(
    component: C,
    options?: StyledOptions<React.ComponentProps<C>>
  ): CreateStyledComponent<
    PropsOf<C> & {
      theme?: Theme
    }
  >

  <
    Tag extends keyof ReactJSXIntrinsicElements,
    ForwardedProps extends keyof ReactJSXIntrinsicElements[Tag] &
      string = keyof ReactJSXIntrinsicElements[Tag] & string
  >(
    tag: Tag,
    options: FilteringStyledOptions<
      ReactJSXIntrinsicElements[Tag],
      ForwardedProps
    >
  ): CreateStyledComponent<
    { theme?: Theme; as?: React.ElementType },
    Pick<ReactJSXIntrinsicElements[Tag], ForwardedProps>
  >

  <Tag extends keyof ReactJSXIntrinsicElements>(
    tag: Tag,
    options?: StyledOptions<ReactJSXIntrinsicElements[Tag]>
  ): CreateStyledComponent<
    { theme?: Theme; as?: React.ElementType },
    ReactJSXIntrinsicElements[Tag]
  >
}

export type ElementType = React.ElementType & {
  defaultProps?: Partial<any>
  __emotion_real?: ElementType
  __emotion_base?: ElementType
  __emotion_styles?: Interpolation<Theme>[]
  __emotion_forwardProp?: (propName: string) => boolean
}
