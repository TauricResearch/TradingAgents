import { createMacro } from 'babel-plugin-macros'

/*
type Transformer = Function
*/

export function createTransformerMacro(
  transformers /*: { [key: string]: Transformer | [Transformer, Object] } */,
  { importSource } /*: { importSource: string } */
) {
  let macro = createMacro(
    ({ path, source, references, state, babel, isEmotionCall }) => {
      if (!path) {
        path = state.file.scope.path
          .get('body')
          .find(p => p.isImportDeclaration() && p.node.source.value === source)
      }

      if (/\/macro$/.test(source)) {
        path
          .get('source')
          .replaceWith(
            babel.types.stringLiteral(source.replace(/\/macro$/, ''))
          )
      }

      if (!isEmotionCall) {
        state.emotionSourceMap = true
      }
      Object.keys(references).forEach(importSpecifierName => {
        if (transformers[importSpecifierName]) {
          references[importSpecifierName].reverse().forEach(reference => {
            let options
            let transformer
            if (Array.isArray(transformers[importSpecifierName])) {
              transformer = transformers[importSpecifierName][0]
              options = transformers[importSpecifierName][1]
            } else {
              transformer = transformers[importSpecifierName]
              options = {}
            }
            transformer({
              state,
              babel,
              path,
              importSource,
              importSpecifierName,
              options,
              reference
            })
          })
        }
      })
      return { keepImports: true }
    }
  )
  macro.transformers = transformers
  return macro
}
