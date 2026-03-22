import { serializeStyles } from '@emotion/serialize'
import minify from './minify'
import { getLabelFromPath } from './label'
import { getSourceMap } from './source-maps'
import { simplifyObject } from './object-to-string'
import {
  appendStringReturningExpressionToArguments,
  joinStringLiterals
} from './strings'
import createNodeEnvConditional from './create-node-env-conditional'

const CSS_OBJECT_STRINGIFIED_ERROR =
  "You have tried to stringify object returned from `css` function. It isn't supposed to be used directly (e.g. as value of the `className` prop), but rather handed to emotion so it can handle it (e.g. as value of `css` prop)."

export let transformExpressionWithStyles = (
  { babel, state, path, shouldLabel, sourceMap = '' } /*: {
  babel,
  state,
  path,
  shouldLabel: boolean,
  sourceMap?: string
} */
) => {
  const autoLabel = state.opts.autoLabel || 'dev-only'
  let t = babel.types
  if (t.isTaggedTemplateExpression(path)) {
    if (
      !sourceMap &&
      state.emotionSourceMap &&
      path.node.quasi.loc !== undefined
    ) {
      sourceMap = getSourceMap(path.node.quasi.loc.start, state)
    }
    minify(path, t)
  }

  if (t.isCallExpression(path)) {
    const canAppendStrings = path.node.arguments.every(
      arg => arg.type !== 'SpreadElement'
    )

    path.get('arguments').forEach(node => {
      if (t.isObjectExpression(node)) {
        node.replaceWith(simplifyObject(node.node, t))
      }
    })

    path.node.arguments = joinStringLiterals(path.node.arguments, t)

    if (
      !sourceMap &&
      canAppendStrings &&
      state.emotionSourceMap &&
      path.node.loc !== undefined
    ) {
      sourceMap = getSourceMap(path.node.loc.start, state)
    }

    const label =
      shouldLabel && autoLabel !== 'never'
        ? getLabelFromPath(path, state, t)
        : null

    if (
      path.node.arguments.length === 1 &&
      t.isStringLiteral(path.node.arguments[0])
    ) {
      let cssString = path.node.arguments[0].value.replace(/;$/, '')
      let res = serializeStyles([
        `${cssString}${
          label && autoLabel === 'always' ? `;label:${label};` : ''
        }`
      ])
      let prodNode = t.objectExpression([
        t.objectProperty(t.identifier('name'), t.stringLiteral(res.name)),
        t.objectProperty(t.identifier('styles'), t.stringLiteral(res.styles))
      ])

      if (!state.emotionStringifiedCssId) {
        const uid = state.file.scope.generateUidIdentifier(
          '__EMOTION_STRINGIFIED_CSS_ERROR__'
        )
        state.emotionStringifiedCssId = uid
        const cssObjectToString = t.functionDeclaration(
          uid,
          [],
          t.blockStatement([
            t.returnStatement(t.stringLiteral(CSS_OBJECT_STRINGIFIED_ERROR))
          ])
        )
        cssObjectToString._compact = true
        state.file.path.unshiftContainer('body', [cssObjectToString])
      }

      if (label && autoLabel === 'dev-only') {
        res = serializeStyles([`${cssString};label:${label};`])
      }

      let devNode = t.objectExpression(
        [
          t.objectProperty(t.identifier('name'), t.stringLiteral(res.name)),
          t.objectProperty(
            t.identifier('styles'),
            t.stringLiteral(res.styles + sourceMap)
          ),
          t.objectProperty(
            t.identifier('toString'),
            t.cloneNode(state.emotionStringifiedCssId)
          )
        ].filter(Boolean)
      )

      return createNodeEnvConditional(t, prodNode, devNode)
    }

    if (canAppendStrings && label) {
      const labelString = `;label:${label};`

      switch (autoLabel) {
        case 'dev-only': {
          const labelConditional = createNodeEnvConditional(
            t,
            t.stringLiteral(''),
            t.stringLiteral(labelString)
          )
          appendStringReturningExpressionToArguments(t, path, labelConditional)
          break
        }
        case 'always':
          appendStringReturningExpressionToArguments(t, path, labelString)
          break
      }
    }

    if (sourceMap) {
      let sourceMapConditional = createNodeEnvConditional(
        t,
        t.stringLiteral(''),
        t.stringLiteral(sourceMap)
      )
      appendStringReturningExpressionToArguments(t, path, sourceMapConditional)
    }
  }
}
