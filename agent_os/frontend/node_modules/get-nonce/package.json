{
  "name": "get-nonce",
  "version": "1.0.1",
  "description": "returns nonce",
  "main": "dist/es5/index.js",
  "types": "dist/es5/index.d.ts",
  "sideEffects": false,
  "repository": "git@github.com:theKashey/get-nonce.git",
  "homepage": "https://github.com/theKashey/get-nonce",
  "author": "Anton Korzunov <thekashey@gmail.com>",
  "license": "MIT",
  "keywords": [
    "webpack",
    "nonce",
    "__webpack_nonce__"
  ],
  "devDependencies": {
    "@theuiteam/lib-builder": "^0.0.10",
    "@size-limit/preset-small-lib": "^2.1.6"
  },
  "module": "dist/es2015/index.js",
  "engines": {
    "node": ">=6"
  },
  "scripts": {
    "dev": "lib-builder dev",
    "test": "jest",
    "test:ci": "jest --runInBand --coverage",
    "build": "lib-builder build && yarn size:report",
    "release": "yarn build && yarn test",
    "size": "npx size-limit",
    "size:report": "npx size-limit --json > .size.json",
    "lint": "lib-builder lint",
    "format": "lib-builder format",
    "update": "lib-builder update",
    "docz:dev": "docz dev",
    "docz:build": "docz build",
    "prepublish": "yarn build && yarn changelog",
    "changelog": "conventional-changelog -p angular -i CHANGELOG.md -s",
    "changelog:rewrite": "conventional-changelog -p angular -i CHANGELOG.md -s -r 0"
  },
  "files": [
    "dist"
  ],
  "husky": {
    "hooks": {
      "pre-commit": "lint-staged"
    }
  },
  "lint-staged": {
    "*.{ts,tsx}": [
      "prettier --write",
      "tslint --fix",
      "git add"
    ],
    "*.{js,css,json,md}": [
      "prettier --write",
      "git add"
    ]
  },
  "prettier": {
    "printWidth": 120,
    "trailingComma": "es5",
    "tabWidth": 2,
    "semi": true,
    "singleQuote": true
  }
}
