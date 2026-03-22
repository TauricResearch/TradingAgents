// this only works correctly in modules, but we don't run on scripts anyway, so it's fine
// the difference is that in modules template objects are being cached per call site
export function getTypeScriptMakeTemplateObjectPath(path) {
  if (path.node.arguments.length === 0) {
    return null
  }

  const firstArgPath = path.get('arguments')[0]

  if (
    firstArgPath.isLogicalExpression() &&
    firstArgPath.get('left').isIdentifier() &&
    firstArgPath.get('right').isAssignmentExpression() &&
    firstArgPath.get('right.right').isCallExpression() &&
    firstArgPath.get('right.right.callee').isIdentifier() &&
    firstArgPath.node.right.right.callee.name.includes('makeTemplateObject') &&
    firstArgPath.node.right.right.arguments.length === 2
  ) {
    return firstArgPath.get('right.right')
  }

  return null
}

// this is only used to prevent appending strings/expressions to arguments incorectly
// we could push them to found array expressions, as we do it for TS-transpile output ¯\_(ツ)_/¯
// it seems overly complicated though - mainly because we'd also have to check against existing stuff of a particular type (source maps & labels)
// considering Babel double-transpilation as a valid use case seems rather far-fetched
export function isTaggedTemplateTranspiledByBabel(path) {
  if (path.node.arguments.length === 0) {
    return false
  }

  const firstArgPath = path.get('arguments')[0]

  if (
    !firstArgPath.isCallExpression() ||
    !firstArgPath.get('callee').isIdentifier()
  ) {
    return false
  }

  const calleeName = firstArgPath.node.callee.name

  if (!calleeName.includes('templateObject')) {
    return false
  }

  const bindingPath = path.scope.getBinding(calleeName).path

  if (!bindingPath.isFunction()) {
    return false
  }

  const functionBody = bindingPath.get('body.body')

  if (!functionBody[0].isVariableDeclaration()) {
    return false
  }

  const declarationInit = functionBody[0].get('declarations')[0].get('init')

  if (!declarationInit.isCallExpression()) {
    return false
  }

  const declarationInitArguments = declarationInit.get('arguments')

  if (
    declarationInitArguments.length === 0 ||
    declarationInitArguments.length > 2 ||
    declarationInitArguments.some(argPath => !argPath.isArrayExpression())
  ) {
    return false
  }

  return true
}
