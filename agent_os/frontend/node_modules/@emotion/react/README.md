# @emotion/react

> Simple styling in React.

## Install

```bash
yarn add @emotion/react
```

## Usage

```jsx
/** @jsx jsx */
import { jsx, css, Global, ClassNames } from '@emotion/react'

render(
  <div css={{ color: 'hotpink' }}>
    <div
      css={css`
        color: green;
      `}
    />
    <Global
      styles={{
        body: {
          margin: 0,
          padding: 0
        }
      }}
    />
    <ClassNames>
      {({ css, cx }) => (
        <div
          className={cx(
            'some-class',
            css`
              color: yellow;
            `
          )}
        />
      )}
    </ClassNames>
  </div>
)
```

More documentation is available at [https://emotion.sh](https://emotion.sh).
