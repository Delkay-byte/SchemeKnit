#!/usr/bin/env node
/**
 * Apply the reviewed single-branch repeated-extglob ReDoS fix
 * (CVE-2026-112366 / GHSA-fc5q-39xc-vjpf) to every installed picomatch copy.
 *
 * Upstream has no patched release. The fix follows the reviewed logic in
 * micromatch/picomatch PR #246 (head f03bec2c02e46f063fbfdc161aae1d0f854b2565):
 * collapse a single all-literal/star branch under `+(...)`/`*(...)` so it can
 * never compile to a nested unbounded quantifier. Capture mode falls back to the
 * existing literal escape, exactly as that proposal does.
 *
 * Run from `frontend/` after npm install. Idempotent. Fails loudly if an
 * upstream file no longer contains the reviewed anchors, so a future picomatch
 * update cannot silently ship unpatched.
 */
'use strict'

const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const NODE_MODULES = path.join(ROOT, 'node_modules')

const HELPER = `// For a single branch of literals and stars, a star can absorb any further
// repetitions of that branch. Keep paths, quoting and other glob/regex syntax
// out of this rewrite: they need their own analysis.
const isSelfRepeatingStarBranch = branch => {
  return branch.includes('*') &&
    !branch.includes('**') &&
    !/[\\\\/"?()[\\]{}|!+@]/.test(branch);
};

`

const COLLAPSE = `  if (branches.length === 1 && isSelfRepeatingStarBranch(branches[0])) {
    // Collapsing changes repeated captures. Use the existing literal fallback
    // instead of exposing a backtracking expression in capture mode.
    return options.capture === true ? { risky: true } : { risky: false, collapse: true };
  }

`

const CLOSE = `    if (analysis.collapse === true && (token.type === 'plus' || token.type === 'star')) {
      token.close = token.type === 'plus' ? ')' : ')?';
    }

`

function findPicomatchDirs(dir, depth = 0, out = []) {
  if (depth > 8) return out
  let entries
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true })
  } catch {
    return out
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const full = path.join(dir, entry.name)
    if (entry.name === 'picomatch') {
      const manifest = path.join(full, 'package.json')
      const parseFile = path.join(full, 'lib', 'parse.js')
      if (fs.existsSync(manifest) && fs.existsSync(parseFile) &&
          !full.split(path.sep).includes('compiled')) {
        out.push(full)
      }
      continue
    }
    if (entry.name === '.bin') continue
    findPicomatchDirs(full, depth + 1, out)
  }
  return out
}

const SUPPORTED_VERSIONS = new Set(['2.3.2', '4.0.7'])

function patchFile(file) {
  const original = fs.readFileSync(file, 'utf8')
  if (original.includes('isSelfRepeatingStarBranch')) {
    if (!original.includes('analysis.collapse === true')) {
      throw new Error(`partially patched picomatch source: ${file}`)
    }
    return 'already'
  }
  for (const anchor of [
    'const analyzeRepeatedExtglob = (body, options) => {',
    '  const branches = splitTopLevel(body).map(branch => branch.trim());',
    "    let output = token.close + (opts.capture ? ')' : '');",
  ]) {
    if (!original.includes(anchor)) {
      throw new Error(`picomatch patch anchor missing in ${file}: ${anchor}`)
    }
  }

  let patched = original.replace(
    'const analyzeRepeatedExtglob = (body, options) => {',
    HELPER + 'const analyzeRepeatedExtglob = (body, options) => {',
  )
  patched = patched.replace(
    '  const branches = splitTopLevel(body).map(branch => branch.trim());\n',
    '  const branches = splitTopLevel(body).map(branch => branch.trim());\n\n' + COLLAPSE,
  )
  patched = patched.replace(
    "    let output = token.close + (opts.capture ? ')' : '');",
    CLOSE + "    let output = token.close + (opts.capture ? ')' : '');",
  )
  for (const marker of [
    'isSelfRepeatingStarBranch',
    'analysis.collapse === true',
  ]) {
    if (!patched.includes(marker)) {
      throw new Error(`picomatch patch verification failed in ${file}: ${marker}`)
    }
  }
  fs.writeFileSync(file, patched)
  const written = fs.readFileSync(file, 'utf8')
  if (!written.includes('isSelfRepeatingStarBranch') ||
      !written.includes('analysis.collapse === true')) {
    throw new Error(`picomatch patch did not persist in ${file}`)
  }
  return 'patched'
}

function patchNextBundle() {
  const nextDir = path.join(NODE_MODULES, 'next')
  const bundle = path.join(nextDir, 'dist', 'compiled', 'picomatch', 'index.js')
  if (!fs.existsSync(nextDir)) return 'absent'
  if (!fs.existsSync(bundle)) {
    throw new Error(
      `Next.js is installed but its compiled picomatch bundle is missing: ${bundle}`)
  }
  const original = fs.readFileSync(bundle, 'utf8')
  if (original.includes('schemeKnitReDoS-capture')) return 'already'
  const anchor = 'const extglobClose=t=>{let n=t.close+(u.capture?")":"");let o;'
  if (!original.includes(anchor)) {
    throw new Error(`Next.js bundled picomatch anchor missing in ${bundle}`)
  }
  const insertion =
    'const extglobClose=t=>{/*schemeKnitReDoS*/' +
    'if((t.type==="plus"||t.type==="star")&&t.inner&&t.inner.includes("*")' +
    '&&!t.inner.includes("**")&&!/[\\\\/"?()[\\]{}|!+@]/.test(t.inner)' +
    '&&u.capture!==true)' +
    '{t.close=t.type==="plus"?")":")?"}' +
    'let n=t.close+(u.capture?")":"");let o;'
  const captureGuard = [
    ';/*schemeKnitReDoS-capture*/',
    'const __skOrig=module.exports;',
    'const __skUnsafe=p=>{',
    '  if(typeof p!=="string")return false;',
    '  const m=/^([^()]*)([+*])\\(([^()]*)\\)([^()]*)$/.exec(p);',
    '  if(!m)return false;',
    '  const body=m[3];',
    '  return body.includes("*")&&!body.includes("**")',
    '    &&!/[\\\\/"?()[\\]{}|!+@]/.test(body);',
    '};',
    'const __skLiteral=p=>p.replace(/[.*+?^${}()|[\\]\\\\]/g,"\\\\$&");',
    'const __skPattern=(p,o)=>o&&o.capture===true&&__skUnsafe(p)?__skLiteral(p):p;',
    'function __skWrap(p,o){return __skOrig(__skPattern(p,o),o)}',
    'Object.assign(__skWrap,__skOrig);',
    '__skWrap.isMatch=(input,p,o)=>__skOrig.isMatch(input,__skPattern(p,o),o);',
    '__skWrap.makeRe=(p,o,...rest)=>__skOrig.makeRe(__skPattern(p,o),o,...rest);',
    '__skWrap.parse=(p,o)=>__skOrig.parse(__skPattern(p,o),o);',
    'module.exports=__skWrap;',
  ].join('')
  const patched = original.replace(anchor, insertion) + captureGuard
  if (!patched.includes('schemeKnitReDoS*/') ||
      !patched.includes('schemeKnitReDoS-capture*/') ||
      !patched.includes('u.capture!==true')) {
    throw new Error(`Next.js bundled picomatch patch verification failed: ${bundle}`)
  }
  fs.writeFileSync(bundle, patched)
  return 'patched'
}

if (!fs.existsSync(NODE_MODULES)) {
  throw new Error('node_modules is missing; run npm install first')
}

const packages = findPicomatchDirs(NODE_MODULES)
if (!packages.length) {
  throw new Error('No picomatch installation found to patch')
}

const results = packages.map((dir) => {
  const version = JSON.parse(
    fs.readFileSync(path.join(dir, 'package.json'), 'utf8')).version
  if (!SUPPORTED_VERSIONS.has(version)) {
    throw new Error(
      `Unsupported picomatch version ${version} at ${dir}; ` +
      'review and add the security patch before installing.')
  }
  const state = patchFile(path.join(dir, 'lib', 'parse.js'))
  return `${version}:${state}`
})
const seen = new Set(packages.map((dir) => JSON.parse(
  fs.readFileSync(path.join(dir, 'package.json'), 'utf8')).version))
for (const version of SUPPORTED_VERSIONS) {
  if (!seen.has(version)) {
    throw new Error(`Expected installed picomatch ${version} was not found`)
  }
}
results.push(`next-bundled:${patchNextBundle()}`)

console.log(`picomatch ReDoS patch: ${results.join(', ')}`)
