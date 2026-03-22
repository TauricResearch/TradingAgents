import babel from '@rollup/plugin-babel';
import resolve from '@rollup/plugin-node-resolve';

const input = './src/index.ts';

// please update the package.json to reflect any changes here
const bundles = createBundles({
  // the `unpkg` UMD bundle (for usage without a bundler)
  unpkg: {
    format: 'umd',
    targets: 'defaults',
    output: { name: 'color2k' },
  },
  // legacy node bundle (note: this is currently used in jest-resolve)
  main: {
    format: 'cjs',
    targets: 'node 4',
  },
  // the `module` bundle that should support older bundlers that used this entry
  // point. (e.g. webpack 2)
  module: {
    format: 'es',
    // `node 6` is a good target because it's closest to es2015 specified in the
    // rollup spec: https://github.com/rollup/rollup/wiki/pkg.module
    targets: 'node 6',
  },
  exports: {
    // `node 12` is a good target because:
    //
    // this module entry point is used by several bundlers.
    // namely: webpack, @rollup/plugin-node-resolve, wmr (via rollup)
    //
    // the lowest common denominator is **acorn 7** with ecmaVersion `2019`
    // - @rollup/plugin-node-resolve supports as low as rollup 1.2
    // - rollup 1.2 uses acorn 7 with ecmaVersion `2019` https://github.com/rollup/rollup/blob/v1.2.0/src/Module.ts#L105
    // - webpack uses acorn 8 with ecmaVersion latest https://github.com/webpack/webpack/blob/v5.0.0/lib/javascript/JavascriptParser.js#L128
    // - node 12 is the first version to completely support ES2019 https://node.green/#ES2019
    //
    // this module entry point is used by esbuild too.
    // https://esbuild.github.io/api/#how-conditions-work
    import: {
      format: 'es',
      targets: 'node 12',
      extension: 'mjs',
    },
    require: {
      format: 'cjs',
      targets: 'node 12',
    },
  },
});

function createBundles(config, parents = []) {
  if ('targets' in config) {
    const { format, extension = 'js', output, targets } = config;

    return [
      {
        input,
        output: {
          file: `./dist/index.${parents.join('.')}.${format}.${extension}`,
          format,
          sourcemap: true,
          ...output,
        },
        plugins: [
          resolve({ extensions: ['.ts'], modulesOnly: true }),
          babel({
            babelrc: false,
            configFile: false,
            babelHelpers: 'bundled',
            extensions: ['.ts'],
            targets,
            presets: [
              ['@babel/preset-env', { targets }],
              '@babel/preset-typescript',
            ],
          }),
        ],
      },
    ];
  }

  return Object.entries(config).flatMap(([key, subConfig]) =>
    createBundles(subConfig, [...parents, key])
  );
}

export default bundles;
