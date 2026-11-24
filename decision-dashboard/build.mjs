import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('.', import.meta.url)));

const ui = await build({
  entryPoints: [resolve(root, 'app.js')],
  bundle: true,
  format: 'esm',
  platform: 'browser',
  write: false,
  minify: true,
  legalComments: 'inline',
});
const script = ui.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
const template = await readFile(resolve(root, 'template.html'), 'utf8');
const css =
  '/*\n' +
  (await readFile(resolve(root, 'DSH-LICENSE.txt'), 'utf8')) +
  '\n*/\n' +
  (await readFile(resolve(root, 'dsh-theme.css'), 'utf8')) +
  '\n' +
  (await readFile(resolve(root, 'style.css'), 'utf8'));

await writeFile(
  resolve(root, 'index.html'),
  template.replace('/* STYLE */', () => css).replace('/* SCRIPT */', () => script),
  'utf8',
);

await build({
  entryPoints: [resolve(root, 'server.mjs')],
  outfile: resolve(root, 'server.bundle.mjs'),
  bundle: true,
  platform: 'node',
  format: 'esm',
  target: 'node20',
  minify: true,
  legalComments: 'inline',
});
