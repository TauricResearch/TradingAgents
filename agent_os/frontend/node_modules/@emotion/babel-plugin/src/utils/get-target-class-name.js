import findRoot from 'find-root'
import memoize from '@emotion/memoize'
import nodePath from 'path'
import hashString from '@emotion/hash'
import escapeRegexp from 'escape-string-regexp'

let hashArray = (arr /*: Array<string> */) => hashString(arr.join(''))

const unsafeRequire = require

const getPackageRootPath = memoize(filename => findRoot(filename))

const separator = new RegExp(escapeRegexp(nodePath.sep), 'g')

const normalizePath = path => nodePath.normalize(path).replace(separator, '/')

export function getTargetClassName(state, t) {
  if (state.emotionTargetClassNameCount === undefined) {
    state.emotionTargetClassNameCount = 0
  }

  const hasFilepath =
    state.file.opts.filename && state.file.opts.filename !== 'unknown'
  const filename = hasFilepath ? state.file.opts.filename : ''
  // normalize the file path to ignore folder structure
  // outside the current node project and arch-specific delimiters
  let moduleName = ''
  let rootPath = filename

  try {
    rootPath = getPackageRootPath(filename)
    moduleName = unsafeRequire(rootPath + '/package.json').name
  } catch (err) {}

  const finalPath =
    filename === rootPath ? 'root' : filename.slice(rootPath.length)

  const positionInFile = state.emotionTargetClassNameCount++

  const stuffToHash = [moduleName]

  if (finalPath) {
    stuffToHash.push(normalizePath(finalPath))
  } else {
    stuffToHash.push(state.file.code)
  }

  const stableClassName = `e${hashArray(stuffToHash)}${positionInFile}`

  return stableClassName
}
