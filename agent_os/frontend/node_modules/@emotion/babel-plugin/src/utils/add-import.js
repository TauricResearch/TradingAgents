import { addDefault, addNamed } from '@babel/helper-module-imports'

export function addImport(
  state,
  importSource /*: string */,
  importedSpecifier /*: string */,
  nameHint /* ?: string */
) {
  let cacheKey = ['import', importSource, importedSpecifier].join(':')
  if (state[cacheKey] === undefined) {
    let importIdentifier
    if (importedSpecifier === 'default') {
      importIdentifier = addDefault(state.file.path, importSource, { nameHint })
    } else {
      importIdentifier = addNamed(
        state.file.path,
        importedSpecifier,
        importSource,
        {
          nameHint
        }
      )
    }
    state[cacheKey] = importIdentifier.name
  }
  return {
    type: 'Identifier',
    name: state[cacheKey]
  }
}
