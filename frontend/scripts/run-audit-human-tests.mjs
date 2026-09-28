/** Compile + run the audit-human unit tests (node:test, no extra deps).
 *
 * Usage: `npm run test:audit` from the frontend directory.
 * Compiles audit-human/formatters/test with `tsc --noCheck` into a temp
 * dir (type safety is covered by `npm run typecheck`) and executes the
 * result with `node --test`. Cleans up afterwards; non-zero exit on fail.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const root = process.cwd();
const outDir = mkdtempSync(join(tmpdir(), 'audit-human-test-'));
try {
  execFileSync(
    process.execPath,
    [
      join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
      'shared/lib/audit-human.ts',
      'shared/lib/formatters.ts',
      'shared/lib/__tests__/audit-human.test.ts',
      '--noCheck',
      '--outDir', outDir,
      '--module', 'commonjs',
      '--target', 'es2022',
      '--moduleResolution', 'node',
    ],
    { cwd: root, stdio: 'inherit' },
  );
  const { writeFileSync } = await import('node:fs');
  writeFileSync(join(outDir, 'package.json'), '{ "type": "commonjs" }\n');
  execFileSync(
    process.execPath,
    ['--test', join(outDir, 'lib', '__tests__', 'audit-human.test.js')],
    { cwd: root, stdio: 'inherit' },
  );
} finally {
  rmSync(outDir, { recursive: true, force: true });
}
