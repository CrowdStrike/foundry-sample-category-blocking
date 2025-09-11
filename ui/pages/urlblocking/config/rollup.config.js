import { rollupPluginHTML as html } from '@web/rollup-plugin-html';
import { defineConfig } from 'rollup';
import babel from '@rollup/plugin-babel';
import nodeResolve from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import replace from '@rollup/plugin-replace';
import json from '@rollup/plugin-json';
import postcss from 'rollup-plugin-postcss';

export default defineConfig([
  {
    input: ['src/*.html'],
    output: {
      dir: 'src/dist',
      format: "esm",
      sourcemap: false,
    },
    plugins: [
      json(),
      replace({
        preventAssignment: true,
        'process.env.NODE_ENV': JSON.stringify('production')
      }),
      babel({
        presets: ["@babel/preset-react"],
      }),
      commonjs(),
      nodeResolve({
        browser: true,
        exportConditions: 'import',
      }),
      postcss({
        extract: true,
        extensions: [".css"]
      }),
      html()
    ],
    onwarn: (msg, warn) => {
      if (msg.code === 'THIS_IS_UNDEFINED') return;
      if (!/Circular/.test(`${msg}`)) {
        warn(msg)
      }
    }
  }
]);
