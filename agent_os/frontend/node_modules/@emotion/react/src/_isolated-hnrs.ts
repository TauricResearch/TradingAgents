// this file isolates this package that is not tree-shakeable
// and allows it to be dropped - if it stays unused
// it happens thanks to sideEffects: false in our package.json
import hoistNonReactStatics from 'hoist-non-react-statics'

// have to wrap it in a proxy function because Rollup is too damn smart
// and if this module doesn't actually contain any logic of its own
// then Rollup just use 'hoist-non-react-statics' directly in other chunks
export default <
  T extends React.ComponentType<any>,
  S extends React.ComponentType<any>
>(
  targetComponent: T,
  sourceComponent: S
) => hoistNonReactStatics(targetComponent, sourceComponent)
