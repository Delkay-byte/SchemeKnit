// Shared reporting helper for the TeachFlow browser acceptance harness.
// Kept dependency-free so it can be used by any spec-style script.

const results = []

function record(name, pass, detail) {
  results.push({ name, pass, detail })
  const tag = pass ? 'PASS' : 'FAIL'
  console.log(`  [${tag}] ${name}${detail ? ` — ${detail}` : ''}`)
}

function summary(label) {
  const failed = results.filter((r) => !r.pass)
  console.log(`\n${label}: ${results.length - failed.length}/${results.length} checks passed`)
  if (failed.length) {
    console.log('FAILURES:')
    for (const f of failed) console.log(`  - ${f.name}: ${f.detail}`)
  }
  return failed.length === 0
}

module.exports = { record, summary, results }
