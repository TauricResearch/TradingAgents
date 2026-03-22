import {
  getTypeScriptMakeTemplateObjectPath,
  isTaggedTemplateTranspiledByBabel
} from './transpiled-output-utils'

export const appendStringReturningExpressionToArguments = (
  t,
  path,
  expression
) => {
  let lastIndex = path.node.arguments.length - 1
  let last = path.node.arguments[lastIndex]
  if (t.isStringLiteral(last)) {
    if (typeof expression === 'string') {
      path.node.arguments[lastIndex].value += expression
    } else {
      path.node.arguments[lastIndex] = t.binaryExpression('+', last, expression)
    }
  } else {
    const makeTemplateObjectCallPath = getTypeScriptMakeTemplateObjectPath(path)

    if (makeTemplateObjectCallPath) {
      makeTemplateObjectCallPath.get('arguments').forEach(argPath => {
        const elements = argPath.get('elements')
        const lastElement = elements[elements.length - 1]
        if (typeof expression === 'string') {
          lastElement.replaceWith(
            t.stringLiteral(lastElement.node.value + expression)
          )
        } else {
          lastElement.replaceWith(
            t.binaryExpression('+', lastElement.node, t.cloneNode(expression))
          )
        }
      })
    } else if (!isTaggedTemplateTranspiledByBabel(path)) {
      if (typeof expression === 'string') {
        path.node.arguments.push(t.stringLiteral(expression))
      } else {
        path.node.arguments.push(expression)
      }
    }
  }
}

export const joinStringLiterals = (expressions /*: Array<*> */, t) => {
  return expressions.reduce((finalExpressions, currentExpression, i) => {
    if (!t.isStringLiteral(currentExpression)) {
      finalExpressions.push(currentExpression)
    } else if (
      t.isStringLiteral(finalExpressions[finalExpressions.length - 1])
    ) {
      finalExpressions[finalExpressions.length - 1].value +=
        currentExpression.value
    } else {
      finalExpressions.push(currentExpression)
    }
    return finalExpressions
  }, [])
}
