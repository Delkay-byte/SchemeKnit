/**
 * CVE-2026-112366 / GHSA-fc5q-39xc-vjpf regression tests.
 *
 * Discovers EVERY installed picomatch copy (including nested ones) and verifies
 * the reviewed patch on each. Pathological patterns run in child processes with
 * a hard parent timeout so a regression cannot hang the runner.
 */
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const frontend = fileURLToPath(new URL('../../', import.meta.url))
const nodeModules = join(frontend, 'node_modules')
const SUPPORTED = new Set(['2.3.2', '4.0.7'])

function discover(root: string, depth = 0, out: string[] = []): string[] {
  if (depth > 8) return out
  let entries
  try {
    entries = readdirSync(root, { withFileTypes: true })
  } catch {
    return out
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name === '.bin') continue
    const full = join(root, entry.name)
    if (entry.name === 'picomatch') {
      if (existsSync(join(full, 'package.json')) &&
          existsSync(join(full, 'lib/parse.js')) &&
          !full.split(/[\\/]/).includes('compiled')) {
        out.push(full)
      }
      continue
    }
    discover(full, depth + 1, out)
  }
  return out
}

const copies = discover(nodeModules).map((dir) => {
  const version = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8')).version
  return { dir, version }
})

function child(dir: string, body: string): void {
  const script = `const pm=require(${JSON.stringify(dir)});${body}`
  const result = spawnSync(process.execPath, ['-e', script], {
    timeout: 2000,
    encoding: 'utf8',
  })
  assert.equal(result.signal, null, `child timed out for ${dir}: ${result.error?.message}`)
  assert.equal(result.status, 0, result.stderr)
}

test('discovers every installed picomatch copy and supports its version', () => {
  assert.ok(copies.length >= 2, `expected multiple copies, found ${copies.length}`)
  const versions = new Set(copies.map((copy) => copy.version))
  for (const version of SUPPORTED) {
    assert.ok(versions.has(version), `missing reviewed picomatch ${version}`)
  }
  for (const copy of copies) {
    assert.ok(SUPPORTED.has(copy.version),
      `unreviewed picomatch ${copy.version} at ${copy.dir}`)
  }
})

for (const { dir, version } of copies) {
  test(`picomatch ${version}: patch markers present`, () => {
    const source = readFileSync(join(dir, 'lib/parse.js'), 'utf8')
    assert.match(source, /isSelfRepeatingStarBranch/)
    assert.match(source, /analysis\.collapse === true/)
  })

  test(`picomatch ${version}: pathological patterns are bounded`, () => {
    child(dir, `
      const assert=require('node:assert/strict');
      const inputs=['a'.repeat(2000)+'b','a'.repeat(2000)+'!', 'x'+'a'.repeat(2000)];
      const patterns=['+(*)','+(*a)','*(*a)','+(a*)','+(a*b)','*(*.js)','+(*a)c','x+(*a)'];
      const started=Date.now();
      for(const pattern of patterns){
        for(const input of inputs){
          pm.isMatch(input,pattern);
          pm.isMatch(input,pattern,{capture:true});
        }
      }
      assert.ok(Date.now()-started<1500, 'bounded run took '+(Date.now()-started)+'ms');
    `)
  })

  test(`picomatch ${version}: ordinary matching matrix`, () => {
    const pm = require(dir)
    const cases: Array<[string, string, boolean, object?]> = [
      ['file.js', '*.js', true],
      ['file.ts', '*.js', false],
      ['src/a/b.ts', 'src/**/*.ts', true],
      ['src/.hidden/b.ts', 'src/**/*.ts', false],
      ['src/.hidden/b.ts', 'src/**/*.ts', true, { dot: true }],
      ['abc', '+(*)', true],
      ['aaa', '+(*a)', true],
      ['ab', '+(*a)', false],
      ['axbayb', '+(a*b)', true],
      ['axbay', '+(a*b)', false],
      ['foo.js', '*(*.js)', true],
      ['foo.ts', '*(*.js)', false],
      ['abc', '+(*)c', true],
      ['a*', 'a\\**', true],
      ['a*b', '"a*b"', true],
      ['abc', '@(a|b)c', false],
      ['ac', '@(a|b)c', true],
      ['xabc', '!(x)abc', false],
      ['a/.b', 'a*', false, { bash: true }],
      ['a/.b', 'a*', true, { bash: true, dot: true }],
    ]
    for (const [input, pattern, expected, options] of cases) {
      assert.equal(pm.isMatch(input, pattern, options), expected,
        `${version} ${pattern} vs ${JSON.stringify(input)}`)
    }
  })

  test(`picomatch ${version}: collapse preserves unguarded semantics`, () => {
    const pm = require(dir)
    const patterns = ['+(*)', '+(*a)', '*(*a)', '+(a*)', '+(a*b)', '*(*.js)', '+(*)c']
    const inputs = ['', 'a', 'aa', 'ab', 'a.a', '.a', 'abc', 'axbayb', 'foo.js', 'foo.ts']
    for (const pattern of patterns) {
      for (const input of inputs) {
        const guarded = pm.makeRe(pattern).exec(input)
        const unguarded = pm.makeRe(pattern, { maxExtglobRecursion: false }).exec(input)
        assert.deepEqual(
          guarded && Array.from(guarded),
          unguarded && Array.from(unguarded),
          `${version} ${pattern} vs ${JSON.stringify(input)}`,
        )
      }
    }
  })
}

test('Next.js bundled copy is patched in normal and capture mode', () => {
  const bundle = join(frontend, 'node_modules/next/dist/compiled/picomatch/index.js')
  assert.ok(existsSync(bundle), 'Next bundled picomatch missing')
  const source = readFileSync(bundle, 'utf8')
  assert.match(source, /schemeKnitReDoS\*\//)
  assert.match(source, /schemeKnitReDoS-capture\*\//)
  assert.match(source, /u\.capture!==true/)

  child(bundle, `
    const assert=require('node:assert/strict');
    const safe=pm.makeRe('+(*a)').source;
    assert.ok(!/\\)\\+/.test(safe), 'normal mode still nests quantifiers: '+safe);
    const cap=pm.makeRe('+(*a)',{capture:true}).source;
    assert.ok(!/\\)\\+/.test(cap), 'capture mode still nests quantifiers: '+cap);
    const started=Date.now();
    assert.equal(pm.isMatch('a'.repeat(2000)+'b','+(*a)'), false);
    assert.equal(pm.isMatch('a'.repeat(2000)+'b','+(*a)',{capture:true}), false);
    assert.equal(pm.isMatch('aaa','+(*a)'), true);
    assert.equal(pm.isMatch('aaa','+(*a)',{capture:true}), false);
    assert.equal(pm.isMatch('+(*a)','+(*a)',{capture:true}), true);
    assert.ok(Date.now()-started<1500);
  `)
})

test('bounded performance across increasing input lengths', () => {
  for (const { dir, version } of copies) {
    child(dir, `
      const assert=require('node:assert/strict');
      for(const n of [100,500,2000,8000]){
        const input='a'.repeat(n)+'b';
        const started=Date.now();
        assert.equal(pm.isMatch(input,'+(*a)'),false);
        assert.ok(Date.now()-started<500, ${JSON.stringify(version)}+' n='+n+' too slow');
      }
    `)
  }
})
