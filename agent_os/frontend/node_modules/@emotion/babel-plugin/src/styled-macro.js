import {
  transformExpressionWithStyles,
  getStyledOptions,
  addImport,
  createTransformerMacro
} from './utils'

const getReferencedSpecifier = (path, specifierName) => {
  const specifiers = path.get('specifiers')
  return specifierName === 'default'
    ? specifiers.find(p => p.isImportDefaultSpecifier())
    : specifiers.find(p => p.node.local.name === specifierName)
}

export let styledTransformer = (
  {
    state,
    babel,
    path,
    importSource,
    reference,
    importSpecifierName,
    options: { styledBaseImport, isWeb }
  } /*: {
  state: Object,
  babel: Object,
  path: any,
  importSource: string,
  importSpecifierName: string,
  reference: Object,
  options: { styledBaseImport?: [string, string], isWeb: boolean }
} */
) => {
  let t = babel.types

  let getStyledIdentifier = () => {
    if (
      !styledBaseImport ||
      (styledBaseImport[0] === importSource &&
        styledBaseImport[1] === importSpecifierName)
    ) {
      return t.cloneNode(reference.node)
    }

    if (path.node) {
      const referencedSpecifier = getReferencedSpecifier(
        path,
        importSpecifierName
      )

      if (referencedSpecifier) {
        referencedSpecifier.remove()
      }

      if (!path.get('specifiers').length) {
        path.remove()
      }
    }

    const [baseImportSource, baseSpecifierName] = styledBaseImport

    return addImport(state, baseImportSource, baseSpecifierName, 'styled')
  }
  let createStyledComponentPath = null
  if (
    t.isMemberExpression(reference.parent) &&
    reference.parent.computed === false
  ) {
    if (
      // checks if the first character is lowercase
      // becasue we don't want to transform the member expression if
      // it's in primitives/native
      reference.parent.property.name.charCodeAt(0) > 96
    ) {
      reference.parentPath.replaceWith(
        t.callExpression(getStyledIdentifier(), [
          t.stringLiteral(reference.parent.property.name)
        ])
      )
    } else {
      reference.replaceWith(getStyledIdentifier())
    }

    createStyledComponentPath = reference.parentPath
  } else if (
    reference.parentPath &&
    t.isCallExpression(reference.parentPath) &&
    reference.parent.callee === reference.node
  ) {
    reference.replaceWith(getStyledIdentifier())
    createStyledComponentPath = reference.parentPath
  }

  if (!createStyledComponentPath) {
    return
  }

  const styledCallLikeWithStylesPath = createStyledComponentPath.parentPath

  let node = transformExpressionWithStyles({
    path: styledCallLikeWithStylesPath,
    state,
    babel,
    shouldLabel: false
  })

  if (node && isWeb) {
    // we know the argument length will be 1 since that's the only time we will have a node since it will be static
    styledCallLikeWithStylesPath.node.arguments[0] = node
  }

  styledCallLikeWithStylesPath.addComment('leading', '#__PURE__')

  if (isWeb) {
    createStyledComponentPath.node.arguments[1] = getStyledOptions(
      t,
      createStyledComponentPath,
      state
    )
  }
}

export let createStyledMacro = (
  {
    importSource,
    originalImportSource = importSource,
    baseImportName = 'default',
    isWeb
  } /*: {
  importSource: string,
  originalImportSource?: string,
  baseImportName?: string,
  isWeb: boolean
} */
) =>
  createTransformerMacro(
    {
      default: [
        styledTransformer,
        { styledBaseImport: [importSource, baseImportName], isWeb }
      ]
    },
    { importSource: originalImportSource }
  )
