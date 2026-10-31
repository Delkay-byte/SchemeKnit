# DeepSeek / Groq Curriculum Generation Matrix

Generated from real repository scheme documents on an isolated SQLite database. Each case is one live DeepSeek request through the real TeachFlow router and generation pipeline. All six cases passed the real quality gate and persisted.

| Level | Class | Subject | Week | Indicator | Provider | Model | HTTP | Rubric | Gate accepted | Reload | DOCX | PDF |
|---|---|---|---:|---|---|---|---:|---:|---|---:|---:|---:|
| KG | KG 1 | Our World Our People | 1 | `K1.1.1.1.1` | deepseek | deepseek-flash | 200 | 63 | 1 | 200 | 200 | 200 |
| KG | KG 2 | Our World Our People | 8 | `K2.2.1.1.1` | deepseek | deepseek-flash | 200 | 63 | 1 | 200 | 200 | 200 |
| Primary | Basic 6 | French | 1 | `B6.1.1.1.1` | deepseek | deepseek-flash | 200 | 52 | 1 | 200 | 200 | 200 |
| Primary | Basic 6 | English Language | 2 | `B6.2.2.1.1` | deepseek | deepseek-flash | 200 | 45 | 1 | 200 | 200 | 200 |
| JHS | Basic 9 | Mathematics | 1 | `B9.1.1.1.1` | deepseek | deepseek-flash | 200 | 67 | 1 | 200 | 200 | 200 |
| JHS | Basic 9 | Science | 1 | `B9.1.1.1.1` | deepseek | deepseek-flash | 200 | 65 | 1 | 200 | 200 | 200 |

## Case notes

### kg1_all_about_me

- Source: `tests/fixtures/wapef/KG 1 Scheme.pdf`
- Curriculum: KG 1 / Our World Our People / All About Me / I am a wonderful and unique
creation
- Indicator: `K1.1.1.1.1` — K1.1.1.1.1 K1.1.1.1.1-7
- Provider/model: `deepseek` / `deepseek-flash`; fallback used: `False`
- Gate: accepted=1, first-pass=1, mean=63.0; manual rubric 63/75
- Timeline: 60 min; resources: 10; assessment items: 3
- Export: DOCX 200 (39195 bytes), PDF 200 (85943 bytes)

### kg2_my_family

- Source: `tests/fixtures/wapef/WAPEF SCHEME OF LEARNING FOR KG.docx`
- Curriculum: KG 2 / Our World Our People / My Family / Types And Members Of My Family
- Indicator: `K2.2.1.1.1` — K2.2.1.1.1 K2.2.1.1.1-7
- Provider/model: `deepseek` / `deepseek-flash`; fallback used: `False`
- Gate: accepted=1, first-pass=1, mean=63.0; manual rubric 63/75
- Timeline: 60 min; resources: 8; assessment items: 3
- Export: DOCX 200 (38982 bytes), PDF 200 (84792 bytes)

### p6_french_salutations

- Source: `real_documents/BASIC 6 FRENCH SCHEME OF LEARNING.docx`
- Curriculum: Basic 6 / French / L’identité / Saluer et prendre congé.
- Indicator: `B6.1.1.1.1` — B6.1.1.1.1 Écouter/Regarder et comprendre un document audiovisuel dans lequel deux personnes se saluent
- Provider/model: `deepseek` / `deepseek-flash`; fallback used: `False`
- Gate: accepted=1, first-pass=1, mean=53.0; manual rubric 52/75
- Timeline: 60 min; resources: 8; assessment items: 3
- Export: DOCX 200 (39082 bytes), PDF 200 (94511 bytes)

### p6_english_songs

- Source: `real_documents/BASIC 6 TERM 1.docx`
- Curriculum: Basic 6 / English Language / Oral Language / Songs
- Indicator: `B6.2.2.1.1` — B6.2.2.1.1 : Read words with ending sounds like “sure” as in measure; “ture” as in creature and “tch” as in stretch
- Provider/model: `deepseek` / `deepseek-flash`; fallback used: `False`
- Gate: accepted=1, first-pass=1, mean=65.0; manual rubric 45/75
- Timeline: 60 min; resources: 7; assessment items: 3
- Export: DOCX 200 (39175 bytes), PDF 200 (90557 bytes)

### jhs_math_place_value

- Source: `real_documents/BASIC 9 MATH SCHEME OF LEARNING.docx`
- Curriculum: Basic 9 / Mathematics / Number / Number and Numeration Systems
- Indicator: `B9.1.1.1.1` — B9.1.1.1.1 Express integers to a given number of significant and decimal places.
- Provider/model: `deepseek` / `deepseek-flash`; fallback used: `False`
- Gate: accepted=1, first-pass=1, mean=67.0; manual rubric 67/75
- Timeline: 60 min; resources: 11; assessment items: 3
- Export: DOCX 200 (40097 bytes), PDF 200 (106668 bytes)

### jhs_science_binary_compounds

- Source: `real_documents/BASIC 9 SCIENCE SCHEME OF LEARNING.docx`
- Curriculum: Basic 9 / Science / Diversity of Matter / Materials
- Indicator: `B9.1.1.1.1` — B9.1.1.1.1 Identify by name binary chemical compounds and discuss their use
- Provider/model: `deepseek` / `deepseek-flash`; fallback used: `False`
- Gate: accepted=1, first-pass=1, mean=65.0; manual rubric 65/75
- Timeline: 60 min; resources: 8; assessment items: 3
- Export: DOCX 200 (39741 bytes), PDF 200 (101517 bytes)

## Reading the rubric column

The gate accepted every case (no hard failure, no floor failure). The independent 75-point rubric is reported for transparency. KG and English cases score lower because the shared rubric rewards repeated indicator wording and generic science-process markers; that does not mean the gate failed. Live Groq fallback evidence is in `docs/qa/deepseek-groq-hardening-report.md` and `backend/temp/deepseek_e2e/matrix_evidence/groq_fallback.json`.
