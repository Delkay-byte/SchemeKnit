#!/usr/bin/env node
/**
 * Fail-closed build guard for the picomatch ReDoS patch.
 *
 * Runs before every build so a skipped postinstall (`--ignore-scripts`) cannot
 * produce a deployment with the vulnerable matcher. Verifies every installed
 * copy and the Next.js bundled copy, then exercises the attack pattern in a
 * short-lived child process with a hard timeout.
 */
'use strict'

const { execFileSync } = require('child_process')
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const NODE_MODULES = path.join(ROOT, 'node_modules')
const SUPPORTED = new Set(['2.3.2', '4.0.7'])

function discover(dir, depth = 0, out = []) {
  if (depth > 8) return out
  let entries
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true })
  } catch {
    return out
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name === '.bin') continue
    const full = path.join(dir, entry.name)
    if (entry.name === 'picomatch') {
      if (fs.existsSync(path.join(full, 'package.json')) &&
          fs.existsSync(path.join(full, 'lib/parse.js')) &&
          !full.split(path.sep).includes('compiled')) {
        out.push(full)
      }
      continue
    }
    discover(full, depth + 1, out)
  }
  return out
}

function verifyMatcher(modulePath) {
  const script = `
    const assert = require('node:assert/strict');
    const pm = require(${JSON.stringify(modulePath)});
    const normal = pm.makeRe('+(*a)').source;
    const capture = pm.makeRe('+(*a)', { capture: true }).source;
    assert.ok(!/\\)\\+/.test(normal), 'normal nested quantifier: ' + normal);
    assert.ok(!/\\)\\+/.test(capture), 'capture nested quantifier: ' + capture);
    assert.equal(pm.isMatch('a'.repeat(2000) + 'b', '+(*a)'), false);
    assert.equal(pm.isMatch('a'.repeat(2000) + 'b', '+(*a)', { capture: true }), false);
    assert.equal(pm.isMatch('aaa', '+(*a)'), true);
    console.log('ok');
  `
  const result = execFileSync(process.execPath, ['-e', script], {
    timeout: 3000,
    encoding: 'utf8',
  })
  if (!result.includes('ok')) throw new Error(`matcher check failed for ${modulePath}`)
}

if (!fs.existsSync(NODE_MODULES)) {
  throw new Error('node_modules missing: install dependencies before building')
}

const copies = discover(NODE_MODULES)
if (!copies.length) throw new Error('no installed picomatch copy found')
const versions = new Set()
for (const dir of copies) {
  const version = JSON.parse(
    fs.readFileSync(path.join(dir, 'package.json'), 'utf8')).version
  if (!SUPPORTED.has(version)) {
    throw new Error(`unreviewed picomatch ${version} at ${dir}`)
  }
  versions.add(version)
  const source = fs.readFileSync(path.join(dir, 'lib', 'parse.js'), 'utf8')
  if (!source.includes('isSelfRepeatingStarBranch')) {
    throw new Error(`picomatch ${version} is not patched at ${dir}`)
  }
  verifyMatcher(dir)
}
for (const version of SUPPORTED) {
  if (!versions.has(version)) throw new Error(`missing picomatch ${version}`)
}

const nextDir = path.join(NODE_MODULES, 'next')
const bundle = path.join(nextDir, 'dist', 'compiled', 'picomatch', 'index.js')
if (!fs.existsSync(nextDir)) throw new Error('next is not installed')
if (!fs.existsSync(bundle)) throw new Error(`missing Next bundled picomatch: ${bundle}`)
const bundleSource = fs.readFileSync(bundle, 'utf8')
for (const marker of ['schemeKnitReDoS*/', 'schemeKnitReDoS-capture*/']) {
  if (!bundleSource.includes(marker)) {
    throw new Error(`Next bundled picomatch missing marker ${marker}`)
  }
}
verifyMatcher(bundle)

console.log(`picomatch security guard: ${[...versions].join(', ')}, next-bundled`)
