import { serializeStyles } from '@emotion/serialize'

// to anyone looking at this, this isn't intended to simplify every single case
// it's meant to simplify the most common cases so i don't want to make it especially complex
// also, this will be unnecessary when prepack is ready
export function simplifyObject(node, t /*: Object */) {
  let finalString = ''
  for (let i = 0; i < node.properties.length; i++) {
    let property = node.properties[i]

    if (
      !t.isObjectProperty(property) ||
      property.computed ||
      (!t.isIdentifier(property.key) && !t.isStringLiteral(property.key)) ||
      (!t.isStringLiteral(property.value) &&
        !t.isNumericLiteral(property.value) &&
        !t.isObjectExpression(property.value))
    ) {
      return node
    }

    let key = property.key.name || property.key.value
    if (key === 'styles') {
      return node
    }
    if (t.isObjectExpression(property.value)) {
      let simplifiedChild = simplifyObject(property.value, t)
      if (!t.isStringLiteral(simplifiedChild)) {
        return node
      }
      finalString += `${key}{${simplifiedChild.value}}`
      continue
    }
    let value = property.value.value

    finalString += serializeStyles([{ [key]: value }]).styles
  }
  return t.stringLiteral(finalString)
}
