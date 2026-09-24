'use client'

import { Fragment, useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Banner } from '@/components/ui/banner'
import { PageHeader } from '@/components/ui/page-header'
import { Upload, FileText, CheckCircle, AlertTriangle } from 'lucide-react'
import { api } from '@/lib/api'
import { WhatsAppButton } from '@/components/whatsapp-button'
import { formatFileSize } from '@/lib/utils-display'

// The three phases the upload screen moves through: the teacher always knows
// where they are in UPLOAD → DETECT → REVIEW.
const FLOW_STEPS = ['Upload', 'Detect', 'Review']

export default function UploadPage() {
  const router = useRouter()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [result, setResult] = useState<any>(null)
  // Multi-subject document confirmation state (§4). When a document contains
  // several subjects the teacher must confirm which section to use.
  const [confirmingSubject, setConfirmingSubject] = useState<string | null>(null)

  const validExtensions = ['.docx', '.pdf']

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      const fileExtension = '.' + selectedFile.name.split('.').pop()?.toLowerCase()
      if (!validExtensions.includes(fileExtension)) {
        setError('Please select a .docx or .pdf file')
        return
      }
      setFile(selectedFile)
      setError(null)
    }
  }

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a file first')
      return
    }

    try {
      setUploading(true)
      setError(null)
      setUploadProgress(0)

      const progressInterval = setInterval(() => {
        setUploadProgress(prev => {
          if (prev >= 90) {
            clearInterval(progressInterval)
            return 90
          }
          return prev + 10
        })
      }, 200)

      const response = await api.uploadScheme(file)

      clearInterval(progressInterval)
      setUploadProgress(100)
      setResult(response)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
      setUploadProgress(0)
    } finally {
      setUploading(false)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const droppedFile = e.dataTransfer.files?.[0]
    if (droppedFile) {
      const ext = '.' + droppedFile.name.split('.').pop()?.toLowerCase()
      if (!validExtensions.includes(ext)) {
        setError('Please select a .docx or .pdf file')
        return
      }
      setFile(droppedFile)
      setError(null)
    }
  }

  const needsSubjectConfirmation = Boolean(result?.detection?.needs_confirmation)
  const detectedSections: { subject: string; week_count?: number }[] =
    result?.detection?.sections?.length
      ? result.detection.sections
      : (result?.detection?.subjects || []).map((s: string) => ({ subject: s }))
  // A genuinely unreadable document (e.g. a scanned/image-only PDF) is a
  // distinct state from "multiple subjects". It must give the teacher an
  // actionable reason instead of a subject picker with no options.
  const isExtractionFailure =
    result?.detection?.status === 'extraction_failed' ||
    result?.extraction?.status === 'extraction_failed' ||
    (result?.weeks_count === 0 && needsSubjectConfirmation && detectedSections.length === 0)
  const extractionReason: string = result?.extraction?.reason || ''
  const extractionFailureMessage =
    extractionReason === 'no_text_layer'
      ? 'This looks like a scanned or image-only PDF, so there is no machine-readable text to read. Export or print it as a text PDF (or run it through OCR such as Adobe Scan), then upload again.'
      : extractionReason === 'no_curriculum_table'
        ? 'No curriculum table could be found in this document. Check that it is the scheme of learning (not a cover page) and that the week/indicator columns are present.'
        : 'We could not reliably read the curriculum content from this document. Review it or upload a clearer copy.'

  const handleConfirmSubject = async (subject: string) => {
    if (!result?.scheme_id) return
    try {
      setConfirmingSubject(subject)
      setError(null)
      await api.confirmSubjectSection(result.scheme_id, subject)
      router.push(`/review/${result.scheme_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not confirm that subject')
    } finally {
      setConfirmingSubject(null)
    }
  }

  const resetToIdle = () => {
    setSuccess(false)
    setResult(null)
    setFile(null)
    setError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  // Flow position: idle = at Upload; uploading/failed/confirmation = at
  // Detect; successful read = at Review.
  const flowCurrent = success
    ? (isExtractionFailure || needsSubjectConfirmation ? 1 : 2)
    : uploading ? 1 : 0

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        <div className="mx-auto max-w-2xl">
          <PageHeader
            className="mb-4"
            eyebrow="Upload"
            title="Upload Your Scheme of Work"
            description="Upload your scheme of work as Word (.docx) or PDF. SchemeKnit
              will automatically extract the curriculum data — including
              documents that contain more than one subject."
          />

          {/* UPLOAD → DETECT → REVIEW — one glance shows the whole flow. */}
          <ol
            data-upload-flow
            aria-label="Upload flow"
            className="mb-6 flex items-center gap-2"
          >
            {FLOW_STEPS.map((label, i) => {
              const state = i < flowCurrent ? 'done' : i === flowCurrent ? 'current' : 'upcoming'
              return (
                <Fragment key={label}>
                  {i > 0 && (
                    <span aria-hidden="true" className="h-0.5 w-6 bg-slate-200 sm:w-10" />
                  )}
                  <li
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider ${
                      state === 'current'
                        ? 'border-[#102A43] bg-[#102A43] text-white'
                        : state === 'done'
                          ? 'border-[#04A9CE]/40 bg-[#04A9CE]/10 text-[#04769B]'
                          : 'border-slate-200 bg-white text-slate-400'
                    }`}
                  >
                    {state === 'done' && <CheckCircle className="h-3.5 w-3.5" aria-hidden="true" />}
                    {label}
                  </li>
                </Fragment>
              )
            })}
          </ol>

          {/* Success State */}
          {success && result ? (
            isExtractionFailure ? (
              /* Extraction failure: honest, actionable, never a dead-end and
                 never a subject picker with nothing to choose from. */
              <div className="space-y-4">
                <Banner tone="danger" title="We could not read this scheme">
                  <p className="font-medium">{result.filename || file?.name}</p>
                  <p className="mt-1">{extractionFailureMessage}</p>
                </Banner>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Button className="flex-1" onClick={resetToIdle}>
                    Upload a different file
                  </Button>
                  <Button variant="outline" className="flex-1" asChild>
                    <Link href="/dashboard">Back to Dashboard</Link>
                  </Button>
                </div>
              </div>
            ) : needsSubjectConfirmation ? (
              /* STEP 4 — multi-subject detection: the teacher must confirm which
                 subject section to use before anything is generated. */
              <SurfaceCard
                data-multi-subject
                accent="bg-gradient-to-r from-amber-400 to-orange-400"
                className="px-5 py-6 sm:px-6"
              >
                <div className="text-center">
                  <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-amber-500" aria-hidden="true" />
                  <h2 className="text-xl font-bold text-[#102A43]">Multiple subjects detected</h2>
                  <p className="mt-1 text-sm font-medium">
                    {result.detection?.title || result.filename || file?.name}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    This document contains more than one subject. Choose the
                    subject you are teaching — SchemeKnit will use only that
                    section.
                  </p>
                </div>
                <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {detectedSections.length === 0 && (
                    <p className="col-span-full text-center text-sm text-muted-foreground">
                      We could not identify a subject heading in this document.
                      Please review the extracted content, or use a clearer copy.
                    </p>
                  )}
                  {detectedSections.map((s, i) => (
                    <Button
                      key={`${s.subject}-${i}`}
                      variant="outline"
                      className="h-auto flex-col gap-1 whitespace-normal py-3 text-left"
                      disabled={confirmingSubject !== null}
                      onClick={() => handleConfirmSubject(s.subject)}
                    >
                      <span className="font-medium">{s.subject}</span>
                      {typeof s.week_count === 'number' && (
                        <span className="text-xs text-muted-foreground">
                          {s.week_count} week{s.week_count === 1 ? '' : 's'}
                        </span>
                      )}
                    </Button>
                  ))}
                </div>
                {confirmingSubject && (
                  <p className="mt-4 text-center text-sm text-muted-foreground">
                    Confirming {confirmingSubject}…
                  </p>
                )}
                {error && (
                  <p className="mt-4 text-center text-sm text-destructive">{error}</p>
                )}
              </SurfaceCard>
            ) : (
              <SurfaceCard
                data-upload-success
                accent="bg-gradient-to-r from-green-500 to-emerald-500"
                className="px-5 py-6 sm:px-6"
              >
                <div className="text-center">
                  <CheckCircle className="mx-auto mb-3 h-12 w-12 text-green-500" aria-hidden="true" />
                  <h2 className="text-xl font-bold text-[#102A43]">Upload successful</h2>
                  <p className="mt-1 text-sm font-medium">{result.filename || file?.name}</p>
                </div>
                <Banner tone="success" className="mt-4" title="Curriculum extracted">
                  <div className="space-y-1 text-sm">
                    {result.subject && <p><strong>Subject:</strong> {result.subject}</p>}
                    {result.class_level && <p><strong>Class:</strong> {result.class_level}</p>}
                    {result.term && <p><strong>Term:</strong> {result.term}</p>}
                    {result.weeks_count && <p><strong>Weeks detected:</strong> {result.weeks_count}</p>}
                    {result.detection?.status === 'single' && (
                      <p className="text-xs">Subject section identified.</p>
                    )}
                    {result.detection?.status === 'low_confidence' && (
                      <p className="text-xs">
                        We could not confidently identify the subject section —
                        please review the extracted content.
                      </p>
                    )}
                  </div>
                </Banner>
                <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                  <Button size="lg" className="flex-1" onClick={() => router.push(`/review/${result.scheme_id}`)}>
                    Review Curriculum
                    <span className="ml-2">→</span>
                  </Button>
                  <Button variant="outline" className="flex-1" asChild>
                    <Link href="/dashboard">Back to Dashboard</Link>
                  </Button>
                </div>
              </SurfaceCard>
            )
          ) : (
            <>
              {/* Dropzone */}
              <SurfaceCard data-dropzone accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]" className="mb-4 p-3">
                <div
                  role="button"
                  tabIndex={0}
                  aria-label={file ? `Selected file: ${file.name}` : 'Choose a .docx or .pdf file'}
                  className={`cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#04A9CE] ${
                    file
                      ? 'border-[#04A9CE] bg-[#04A9CE]/5'
                      : 'border-slate-300 hover:border-[#04A9CE] hover:bg-slate-50'
                  }`}
                  onDragOver={handleDragOver}
                  onDrop={handleDrop}
                  onClick={() => !file && fileInputRef.current?.click()}
                  onKeyDown={(e) => {
                    if (!file && (e.key === 'Enter' || e.key === ' ')) {
                      e.preventDefault()
                      fileInputRef.current?.click()
                    }
                  }}
                >
                  {file ? (
                    <div className="space-y-4">
                      <FileText className="mx-auto h-12 w-12 text-[#04769B]" aria-hidden="true" />
                      <div>
                        <p className="break-all text-lg font-semibold text-[#102A43]">{file.name}</p>
                        <p className="text-sm text-muted-foreground">{formatFileSize(file.size)}</p>
                      </div>
                      <Button
                        variant="outline"
                        onClick={(e) => {
                          e.stopPropagation()
                          setFile(null)
                          if (fileInputRef.current) fileInputRef.current.value = ''
                        }}
                      >
                        Choose Different File
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <Upload className="mx-auto h-12 w-12 text-slate-400" aria-hidden="true" />
                      <div>
                        <p className="text-lg font-semibold text-[#102A43]">
                          Drag &amp; drop your file here
                        </p>
                        <p className="text-sm text-muted-foreground">
                          or click to browse
                        </p>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Word (.docx) or PDF · up to 50 MB
                      </p>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".docx,.pdf"
                        onChange={handleFileSelect}
                        className="hidden"
                      />
                    </div>
                  )}
                </div>

                {/* Progress — deterministic upload progress, announced to AT. */}
                {uploading && (
                  <div className="mt-4 px-2 pb-2">
                    <div className="mb-1 flex justify-between text-sm">
                      <span className="text-muted-foreground">
                        Uploading and extracting curriculum data…
                      </span>
                      <span className="font-medium text-[#102A43]">{uploadProgress}%</span>
                    </div>
                    <div
                      role="progressbar"
                      aria-label="Upload progress"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={uploadProgress}
                      className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
                    >
                      <div
                        className="h-2 rounded-full bg-gradient-to-r from-[#102A43] to-[#04A9CE] transition-all duration-300"
                        style={{ width: `${uploadProgress}%` }}
                      ></div>
                    </div>
                  </div>
                )}
              </SurfaceCard>

              {error && (
                <div className="mb-4">
                  <Banner tone="danger" title="Upload problem">
                    {error}
                  </Banner>
                </div>
              )}

              {/* Actions */}
              <div className="flex flex-col gap-3 sm:flex-row sm:justify-between">
                <Button variant="outline" className="w-full sm:w-auto" asChild>
                  <Link href="/dashboard">Cancel</Link>
                </Button>
                <Button onClick={handleUpload} disabled={!file || uploading} size="lg" className="w-full sm:w-auto">
                  {uploading ? (
                    <>
                      <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-b-2 border-white" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="mr-2 h-4 w-4" />
                      Upload &amp; Process
                    </>
                  )}
                </Button>
              </div>

              {/* Help — what happens after the file leaves this page. */}
              <SurfaceCard className="mt-8 px-5 py-5 sm:px-6">
                <h2 className="text-base font-semibold text-[#102A43]">What happens next?</h2>
                <ol className="mt-3 list-decimal space-y-2 pl-1 text-sm text-muted-foreground list-inside">
                  <li>SchemeKnit extracts curriculum data from your document</li>
                  <li>You review and approve the extracted information</li>
                  <li>You configure lesson plan settings (duration, template, etc.)</li>
                  <li>SchemeKnit generates your lesson plans</li>
                  <li>You review, edit, and export your lesson plans</li>
                </ol>
                <p className="mt-4 text-xs text-muted-foreground">
                  Supported formats: Word (.docx) and PDF. Maximum file size: 50 MB.
                </p>
              </SurfaceCard>
            </>
          )}
        </div>
      </main>
      <WhatsAppButton />
    </div>
  )
}
