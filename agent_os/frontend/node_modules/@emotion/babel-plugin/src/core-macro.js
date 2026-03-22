import {
  transformExpressionWithStyles,
  createTransformerMacro,
  getSourceMap,
  addImport
} from './utils'

export const transformCssCallExpression = (
  { state, babel, path, sourceMap, annotateAsPure = true } /*: {
  state: *,
  babel: *,
  path: *,
  sourceMap?: string,
  annotateAsPure?: boolean
} */
) => {
  let node = transformExpressionWithStyles({
    babel,
    state,
    path,
    shouldLabel: true,
    sourceMap
  })
  if (node) {
    path.replaceWith(node)
    path.hoist()
  } else if (annotateAsPure && path.isCallExpression()) {
    path.addComment('leading', '#__PURE__')
  }
}

export const transformCsslessArrayExpression = (
  { state, babel, path } /*: {
  babel: *,
  state: *,
  path: *
} */
) => {
  let t = babel.types
  let expressionPath = path.get('value.expression')
  let sourceMap =
    state.emotionSourceMap && path.node.loc !== undefined
      ? getSourceMap(path.node.loc.start, state)
      : ''

  expressionPath.replaceWith(
    t.callExpression(
      // the name of this identifier doesn't really matter at all
      // it'll never appear in generated code
      t.identifier('___shouldNeverAppearCSS'),
      path.node.value.expression.elements
    )
  )

  transformCssCallExpression({
    babel,
    state,
    path: expressionPath,
    sourceMap,
    annotateAsPure: false
  })

  if (t.isCallExpression(expressionPath)) {
    expressionPath.replaceWith(t.arrayExpression(expressionPath.node.arguments))
  }
}

export const transformCsslessObjectExpression = (
  { state, babel, path, cssImport } /*: {
  babel: *,
  state: *,
  path: *,
  cssImport: { importSource: string, cssExport: string }
} */
) => {
  let t = babel.types
  let expressionPath = path.get('value.expression')
  let sourceMap =
    state.emotionSourceMap && path.node.loc !== undefined
      ? getSourceMap(path.node.loc.start, state)
      : ''

  expressionPath.replaceWith(
    t.callExpression(
      // the name of this identifier doesn't really matter at all
      // it'll never appear in generated code
      t.identifier('___shouldNeverAppearCSS'),
      [path.node.value.expression]
    )
  )

  transformCssCallExpression({
    babel,
    state,
    path: expressionPath,
    sourceMap
  })

  if (t.isCallExpression(expressionPath)) {
    expressionPath
      .get('callee')
      .replaceWith(
        addImport(state, cssImport.importSource, cssImport.cssExport, 'css')
      )
  }
}

let cssTransformer = (
  { state, babel, reference } /*: {
  state: any,
  babel: any,
  reference: any
} */
) => {
  transformCssCallExpression({ babel, state, path: reference.parentPath })
}

let globalTransformer = (
  { state, babel, reference, importSource, options } /*: {
  state: any,
  babel: any,
  reference: any,
  importSource: string,
  options: { cssExport?: string }
} */
) => {
  const t = babel.types

  if (
    !t.isJSXIdentifier(reference.node) ||
    !t.isJSXOpeningElement(reference.parentPath.node)
  ) {
    return
  }

  const stylesPropPath = reference.parentPath
    .get('attributes')
    .find(p => t.isJSXAttribute(p.node) && p.node.name.name === 'styles')

  if (!stylesPropPath) {
    return
  }

  if (t.isJSXExpressionContainer(stylesPropPath.node.value)) {
    if (t.isArrayExpression(stylesPropPath.node.value.expression)) {
      transformCsslessArrayExpression({
        state,
        babel,
        path: stylesPropPath
      })
    } else if (t.isObjectExpression(stylesPropPath.node.value.expression)) {
      transformCsslessObjectExpression({
        state,
        babel,
        path: stylesPropPath,
        cssImport:
          options.cssExport !== undefined
            ? {
                importSource,
                cssExport: options.cssExport
              }
            : {
                importSource: '@emotion/react',
                cssExport: 'css'
              }
      })
    }
  }
}

export const transformers = {
  // this is an empty function because this transformer is never called
  // we don't run any transforms on `jsx` directly
  // instead we use it as a hint to enable css prop optimization
  jsx: () => {},
  css: cssTransformer,
  Global: globalTransformer
}

export default createTransformerMacro(transformers, {
  importSource: '@emotion/react'
})
