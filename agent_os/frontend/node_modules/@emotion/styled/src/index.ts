import { Theme } from '@emotion/react'
import baseStyled from './base'
import { ReactJSXIntrinsicElements } from './jsx-namespace'
import { tags } from './tags'
import {
  CreateStyledComponent,
  CreateStyled as BaseCreateStyled
} from './types'
export type {
  ArrayInterpolation,
  ComponentSelector,
  CSSObject,
  FunctionInterpolation,
  Interpolation
} from '@emotion/serialize'
export type {
  CreateStyledComponent,
  FilteringStyledOptions,
  StyledComponent,
  StyledOptions
} from './types'

export type StyledTags = {
  [Tag in keyof ReactJSXIntrinsicElements]: CreateStyledComponent<
    {
      theme?: Theme
      as?: React.ElementType
    },
    ReactJSXIntrinsicElements[Tag]
  >
}

export interface CreateStyled extends BaseCreateStyled, StyledTags {}

// bind it to avoid mutating the original function
const styled = baseStyled.bind(null) as CreateStyled

tags.forEach(tagName => {
  ;(styled as any)[tagName] = styled(tagName as keyof typeof styled)
})

export default styled
