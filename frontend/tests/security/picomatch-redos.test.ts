/**
 * CVE-2026-112366 / GHSA-fc5q-39xc-vjpf regression tests.
 *
 * The installed picomatch copies are patched by scripts/patch-picomatch.cjs
 * after npm install. Pathological patterns run in a CHILD process with a hard
 * parent timeout so a regression cannot hang the test runner.
 */
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const frontend = fileURLToPath(new URL('../../', import.meta.url))

function packageDirs(): string[] {
  const candidates = [
    'node_modules/picomatch',
    'node_modules/tinyglobby/node_modules/picomatch',
  ]
  return candidates
    .map((relative) => `${frontend}${relative}`)
    .filter((dir) => existsSync(`${dir}/package.json`))
}

const dirs = packageDirs()

test('every installed picomatch copy contains the reviewed patch', () => {
  assert.ok(dirs.length >= 2, 'expected both installed picomatch copies')
  for (const dir of dirs) {
    const source = readFileSync(`${dir}/lib/parse.js`, 'utf8')
    assert.match(source, /isSelfRepeatingStarBranch/)
    assert.match(source, /analysis\.collapse === true/)
    const pkg = JSON.parse(readFileSync(`${dir}/package.json`, 'utf8'))
    assert.ok(['2.3.2', '4.0.7'].includes(pkg.version), pkg.version)
  }
})

test('vulnerable patterns complete inside a strict child-process timeout', () => {
  for (const dir of dirs) {
    const script = `
      const assert = require('node:assert/strict');
      const pm = require(${JSON.stringify(dir)});
      const inputs = ['a'.repeat(2000) + 'b', 'a'.repeat(2000) + '!'];
      for (const pattern of ['+(*a)', '*(*a)', '+(*a)c', 'x+(*a)', '+(*)']) {
        const started = Date.now();
        for (const input of inputs) {
          pm.isMatch(input, pattern);
          pm.isMatch(input, pattern, { capture: true });
        }
        assert.ok(Date.now() - started < 500, pattern + ' took ' + (Date.now() - started) + 'ms');
      }
      console.log('ok');
    `
    const result = spawnSync(process.execPath, ['-e', script], {
      timeout: 2000,
      encoding: 'utf8',
    })
    assert.equal(result.signal, null, `child timed out for ${dir}: ${result.error?.message}`)
    assert.equal(result.status, 0, result.stderr)
    assert.match(result.stdout, /ok/)
  }
})

test('the Next.js bundled picomatch copy is patched too', () => {
  const bundle = `${frontend}node_modules/next/dist/compiled/picomatch/index.js`
  assert.ok(existsSync(bundle), 'Next bundled picomatch missing')
  const source = readFileSync(bundle, 'utf8')
  assert.match(source, /schemeKnitReDoS/)
  const script = `
    const assert = require('node:assert/strict');
    const pm = require(${JSON.stringify(bundle)});
    const started = Date.now();
    assert.equal(pm.isMatch('a'.repeat(2000) + 'b', '+(*a)'), false);
    assert.equal(pm.isMatch('aaa', '+(*a)'), true);
    assert.ok(Date.now() - started < 500);
    console.log('ok');
  `
  const result = spawnSync(process.execPath, ['-e', script], { timeout: 2000, encoding: 'utf8' })
  assert.equal(result.signal, null, `child timed out: ${result.error?.message}`)
  assert.equal(result.status, 0, result.stderr)
  assert.match(result.stdout, /ok/)
})

test('ordinary glob and extglob matching stays compatible', () => {
  const pm = require(dirs[0])
  const cases: Array<[string, string, boolean]> = [
    ['file.js', '*.js', true],
    ['file.ts', '*.js', false],
    ['src/a/b.ts', 'src/**/*.ts', true],
    ['src/.hidden/b.ts', 'src/**/*.ts', false],
    ['abc', '+(*)', true],
    ['aaa', '+(*a)', true],
    ['ab', '+(*a)', false],
    ['axbayb', '+(a*b)', true],
    ['axbay', '+(a*b)', false],
    ['foo.js', '*(*.js)', true],
    ['foo.ts', '*(*.js)', false],
    ['abc', '+(*)c', true],
  ]
  for (const [input, pattern, expected] of cases) {
    assert.equal(pm.isMatch(input, pattern), expected, `${pattern} vs ${input}`)
  }
})

test('collapse preserves matching against the unguarded matcher', () => {
  const pm = require(dirs[0])
  const patterns = ['+(*)', '+(*a)', '*(*a)', '+(a*)', '+(a*b)', '*(*.js)', '+(*)c']
  const inputs = ['', 'a', 'aa', 'ab', 'a.a', '.a', 'abc', 'axbayb', 'foo.js', 'foo.ts']
  for (const pattern of patterns) {
    for (const input of inputs) {
      const guarded = pm.makeRe(pattern).exec(input)
      const unguarded = pm.makeRe(pattern, { maxExtglobRecursion: false }).exec(input)
      assert.deepEqual(
        guarded && Array.from(guarded),
        unguarded && Array.from(unguarded),
        `${pattern} vs ${JSON.stringify(input)}`,
      )
    }
  }
})

test('nested and multi-branch extglobs keep their existing behaviour', () => {
  const pm = require(dirs[0])
  assert.equal(pm.isMatch('abc', '+(a|bc)'), true)
  assert.equal(pm.isMatch('abab', '+(a|b)a'), false)
  assert.equal(pm.isMatch('abcd', '+(ab|cd)'), true)
  assert.equal(pm.isMatch('ac', '@(a|b)c'), true)
  assert.equal(pm.isMatch('xabc', '!(x)abc'), false)
})
