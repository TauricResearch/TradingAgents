import type { SerializedStyles } from '@emotion/utils'
import type { CSSInterpolation } from '@emotion/serialize'
import { serializeStyles } from '@emotion/serialize'

function css(
  template: TemplateStringsArray,
  ...args: CSSInterpolation[]
): SerializedStyles
function css(...args: CSSInterpolation[]): SerializedStyles
function css(...args: CSSInterpolation[]) {
  return serializeStyles(args)
}

export default css
