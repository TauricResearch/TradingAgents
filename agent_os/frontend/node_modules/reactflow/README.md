![readme-header](https://user-images.githubusercontent.com/3797215/156259138-fb9f59f8-52f2-474a-b78c-6570867e4ead.svg#gh-light-mode-only)

<div align="center">

![GitHub License MIT](https://img.shields.io/github/license/wbkd/react-flow?color=%23ff0072)
![npm downloads](https://img.shields.io/npm/dt/reactflow?color=%23FF0072&label=downloads)
![GitHub Repo stars](https://img.shields.io/github/stars/wbkd/react-flow?color=%23FF0072)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/wbkd/react-flow?color=%23FF0072)

A highly customizable React component for building interactive graphs and node-based editors.

[🚀 Getting Started](https://reactflow.dev/learn/getting-started/installation) | [📖 Documentation](https://reactflow.dev/learn/react-flow) | [📺 Examples](https://reactflow.dev/examples) | [☎️ Discord](https://discord.gg/RVmnytFmGW) | [💎 React Flow Pro](https://pro.reactflow.dev/pricing)

</div>

---

## 🚨 Upcoming Changes 

The main branch is the home of @xyflow/svelte and the upcoming @xyflow/react (React Flow v12). The current version is maintained and lives on the [v11 branch](https://github.com/xyflow/xyflow/tree/v11).


## Key Features

- **Easy to use:** Seamless zooming and panning, single- and multi selection of graph elements and keyboard shortcuts are supported out of the box
- **Customizable:** Different [node](https://reactflow.dev/examples) and [edge types](https://reactflow.dev/examples/edges/edge-types) and support for custom nodes with multiple handles and custom edges
- **Fast rendering:** Only nodes that have changed are re-rendered 
- **Hooks and Utils:** [Hooks](https://reactflow.dev/api-reference/hooks) for handling nodes, edges and the viewport and graph [helper functions](https://reactflow.dev/api-reference/utils)
- **Plugin Components:** [Background](https://reactflow.dev/api-reference/components/background), [MiniMap](https://reactflow.dev/api-reference/components/minimap) and [Controls](https://reactflow.dev/api-reference/components/controls)
- **Reliable**: Written in [Typescript](https://www.typescriptlang.org/) and tested with [cypress](https://www.cypress.io/)

## Commercial Usage

**Are you using React Flow for a personal project?** Great! No sponsorship needed, you can support us by reporting any bugs you find, sending us screenshots of your projects, and starring us on Github 🌟

**Are you using React Flow at your organization and making money from it?** Awesome! We rely on your support to keep React Flow developed and maintained under an MIT License, just how we like it. You can do that on the [React Flow Pro website](https://reactflow.dev/pro) or through [Github Sponsors](https://github.com/sponsors/xyflow).

You can find more information in our [React Flow Pro FAQs](https://reactflow.dev/pro).


## Installation

The easiest way to get the latest version of React Flow is to install it via npm, yarn or pnpm:

```bash
npm install reactflow
```

## Quick Start

This is only a very basic usage example of React Flow. To see everything that is possible with the library, please refer to the [website](https://reactflow.dev) for [guides](https://reactflow.dev/learn/customization/custom-nodes), [examples](https://reactflow.dev/examples) and the full [API reference](https://reactflow.dev/api-reference/react-flow).

```jsx
import { useCallback } from 'react';
import ReactFlow, {
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
} from 'reactflow';

import 'reactflow/dist/style.css';

const initialNodes = [
  { id: '1', position: { x: 0, y: 0 }, data: { label: '1' } },
  { id: '2', position: { x: 0, y: 100 }, data: { label: '2' } },
];

const initialEdges = [{ id: 'e1-2', source: '1', target: '2' }];

function Flow() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect = useCallback((params) => setEdges((eds) => addEdge(params, eds)), [setEdges]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
    >
      <MiniMap />
      <Controls />
      <Background />
    </ReactFlow>
  );
}
```

## Development

Before you can start developing please make sure that you have [pnpm](https://pnpm.io/) installed (`npm i -g pnpm`). Then install the dependencies using pnpm: `pnpm install`.

For local development, you can use `pnpm dev`.

## Testing

Testing is done with cypress. You can find the tests in the [`examples/cypress`](/examples/cypress/) folder. In order to run the tests do:

```sh
pnpm test
```

## Maintainers

React Flow is developed and maintained by [webkid](https://webkid.io), a web development agency with focus on data driven applications from Berlin. If you need help or want to talk to us about a collaboration, feel free to contact us:

- Moritz Klack • [Twitter](https://twitter.com/moklick) • [Github](https://github.com/moklick)
- Christopher Möller • [Twitter](https://twitter.com/chrtze) • [Github](https://github.com/chrtze)

You can also use our [contact form](https://pro.reactflow.dev/contact) or join the [React Flow Discord Server](https://discord.gg/Bqt6xrs).

## Community Packages

- [useUndoable](https://github.com/Infinium8/useUndoable) - Hook for undo/redo functionality with an explicit React Flow example
- [react-flow-smart-edge](https://github.com/tisoap/react-flow-smart-edge) - Custom edge that doesn't intersect with nodes
- [Feliz.ReactFlow](https://github.com/tforkmann/Feliz.ReactFlow) - Feliz React Bindings for React Flow

## Credits

React Flow was initially developed for [datablocks](https://datablocks.pro), a graph-based editor for transforming, analyzing and visualizing data in the browser. Under the hood, React Flow depends on these great libraries:

- [d3-zoom](https://github.com/d3/d3-zoom) - used for zoom, pan and drag interactions with the graph canvas
- [d3-drag](https://github.com/d3/d3-drag) - used for making the nodes draggable
- [zustand](https://github.com/pmndrs/zustand) - internal state management

## License

React Flow is [MIT licensed](https://github.com/xyflow/xyflow/blob/main/LICENSE).
