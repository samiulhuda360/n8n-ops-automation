// Loads the Code-node libraries the same way the builder inlines them: concatenated into one scope.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const JS = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'opsflow', 'js');

export function load(...names) {
  const source = names.map((n) => readFileSync(join(JS, `${n}.js`), 'utf8')).join('\n\n');
  const exported = [...source.matchAll(/^(?:function|const)\s+([A-Za-z_$][\w$]*)/gm)].map((m) => m[1]);
  return new Function(`${source}\nreturn { ${exported.join(', ')} };`)();
}
