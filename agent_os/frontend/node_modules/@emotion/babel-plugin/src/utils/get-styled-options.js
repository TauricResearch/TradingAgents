import { getLabelFromPath } from './label'
import { getTargetClassName } from './get-target-class-name'
import createNodeEnvConditional from './create-node-env-conditional'

const getKnownProperties = (t, node) =>
  new Set(
    node.properties
      .filter(n => t.isObjectProperty(n) && !n.computed)
      .map(n => (t.isIdentifier(n.key) ? n.key.name : n.key.value))
  )

const createObjectSpreadLike = (t, file, ...objs) =>
  t.callExpression(file.addHelper('extends'), [t.objectExpression([]), ...objs])

export let getStyledOptions = (t, path, state) => {
  const autoLabel = state.opts.autoLabel || 'dev-only'

  let args = path.node.arguments
  let optionsArgument = args.length >= 2 ? args[1] : null

  let prodProperties = []
  let devProperties = null
  let knownProperties =
    optionsArgument && t.isObjectExpression(optionsArgument)
      ? getKnownProperties(t, optionsArgument)
      : new Set()

  if (!knownProperties.has('target')) {
    prodProperties.push(
      t.objectProperty(
        t.identifier('target'),
        t.stringLiteral(getTargetClassName(state, t))
      )
    )
  }

  let label =
    autoLabel !== 'never' && !knownProperties.has('label')
      ? getLabelFromPath(path, state, t)
      : null

  if (label) {
    const labelNode = t.objectProperty(
      t.identifier('label'),
      t.stringLiteral(label)
    )
    switch (autoLabel) {
      case 'always':
        prodProperties.push(labelNode)
        break
      case 'dev-only':
        devProperties = [labelNode]
        break
    }
  }

  if (optionsArgument) {
    // for some reason `.withComponent` transformer gets requeued
    // so check if this has been already transpiled to avoid double wrapping
    if (
      t.isConditionalExpression(optionsArgument) &&
      t.isBinaryExpression(optionsArgument.test) &&
      t.buildMatchMemberExpression('process.env.NODE_ENV')(
        optionsArgument.test.left
      )
    ) {
      return optionsArgument
    }
    if (!t.isObjectExpression(optionsArgument)) {
      const prodNode = createObjectSpreadLike(
        t,
        state.file,
        t.objectExpression(prodProperties),
        optionsArgument
      )
      return devProperties
        ? createNodeEnvConditional(
            t,
            prodNode,
            t.cloneNode(
              createObjectSpreadLike(
                t,
                state.file,
                t.objectExpression(prodProperties.concat(devProperties)),
                optionsArgument
              )
            )
          )
        : prodNode
    }

    prodProperties.unshift(...optionsArgument.properties)
  }

  return devProperties
    ? createNodeEnvConditional(
        t,
        t.objectExpression(prodProperties),
        t.cloneNode(t.objectExpression(prodProperties.concat(devProperties)))
      )
    : t.objectExpression(prodProperties)
}
