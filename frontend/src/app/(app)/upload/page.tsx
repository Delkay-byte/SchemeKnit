'use client'

import { useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { PageHeader } from '@/components/ui/page-header'
import { Upload, FileText, CheckCircle, AlertTriangle } from 'lucide-react'
import { api } from '@/lib/api'
import { WhatsAppButton } from '@/components/whatsapp-button'
import { formatFileSize } from '@/lib/utils-display'

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

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        <div className="max-w-2xl mx-auto">
          {/* Success State */}
          {success && result ? (
            isExtractionFailure ? (
              /* Extraction failure: honest, actionable, never a dead-end and
                 never a subject picker with nothing to choose from. */
              <Card className="border-red-200 bg-red-50">
                <CardContent className="p-8">
                  <div className="text-center">
                    <AlertTriangle className="h-12 w-12 text-red-500 mx-auto mb-3" />
                    <h2 className="text-xl font-bold mb-2">We could not read this scheme</h2>
                    <p className="text-sm font-medium mb-1">
                      {result.filename || file?.name}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {extractionFailureMessage}
                    </p>
                  </div>
                  <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-center">
                    <Button
                      onClick={() => {
                        setSuccess(false)
                        setResult(null)
                        setFile(null)
                        setError(null)
                        if (fileInputRef.current) fileInputRef.current.value = ''
                      }}
                    >
                      Upload a different file
                    </Button>
                    <Link href="/dashboard">
                      <Button variant="outline" className="w-full">Back to Dashboard</Button>
                    </Link>
                  </div>
                </CardContent>
              </Card>
            ) : needsSubjectConfirmation ? (
              /* STEP 4 — multi-subject detection: the teacher must confirm which
                 subject section to use before anything is generated. */
              <Card className="border-amber-200 bg-amber-50">
                <CardContent className="p-8">
                  <div className="text-center">
                    <AlertTriangle className="h-12 w-12 text-amber-500 mx-auto mb-3" />
                    <h2 className="text-xl font-bold mb-2">Multiple subjects detected</h2>
                    <p className="text-sm font-medium mb-1">
                      {result.detection?.title || result.filename || file?.name}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      This document contains more than one subject. Choose the
                      subject you are teaching — SchemeKnit will use only that
                      section.
                    </p>
                  </div>
                  <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 gap-3">
                    {detectedSections.length === 0 && (
                      <p className="col-span-full text-sm text-muted-foreground text-center">
                        We could not identify a subject heading in this document.
                        Please review the extracted content, or use a clearer copy.
                      </p>
                    )}
                    {detectedSections.map((s, i) => (
                      <Button
                        key={`${s.subject}-${i}`}
                        variant="outline"
                        className="h-auto py-3 flex flex-col gap-1 whitespace-normal text-left"
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
                    <p className="mt-4 text-sm text-muted-foreground text-center">
                      Confirming {confirmingSubject}…
                    </p>
                  )}
                  {error && (
                    <p className="mt-4 text-sm text-destructive text-center">{error}</p>
                  )}
                </CardContent>
              </Card>
            ) : (
            <Card className="border-green-200 bg-green-50">
              <CardContent className="p-8 text-center">
                <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
                <h2 className="text-xl font-bold mb-2">Upload successful</h2>
                <p className="text-sm font-medium mb-4">{result.filename || file?.name}</p>
                <div className="space-y-1 text-sm text-muted-foreground mb-6">
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
                <div className="flex flex-col sm:flex-row gap-3 justify-center">
                  <Button size="lg" onClick={() => router.push(`/review/${result.scheme_id}`)}>
                    Review Curriculum
                    <span className="ml-2">→</span>
                  </Button>
                </div>
              </CardContent>
            </Card>
            )
          ) : (
            <>
              {/* Upload Area */}
              <PageHeader
                className="mb-6"
                eyebrow="Upload"
                title="Upload Your Scheme of Work"
                description="Upload your scheme of work as Word (.docx) or PDF. SchemeKnit
                  will automatically extract the curriculum data — including
                  documents that contain more than one subject."
              />
              <Card className="mb-6">
                <CardContent>
                  <div
                    className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                      file ? 'border-green-500 bg-green-50' : 'border-gray-300 hover:border-primary cursor-pointer'
                    }`}
                    onDragOver={handleDragOver}
                    onDrop={handleDrop}
                    onClick={() => !file && fileInputRef.current?.click()}
                  >
                    {file ? (
                      <div className="space-y-4">
                        <FileText className="h-16 w-16 text-green-500 mx-auto" />
                        <div>
                          <p className="text-lg font-semibold">{file.name}</p>
                          <p className="text-sm text-muted-foreground">
                            {formatFileSize(file.size)}
                          </p>
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
                        <Upload className="h-16 w-16 text-muted-foreground mx-auto" />
                        <div>
                          <p className="text-lg font-semibold">
                            Drag & drop your file here
                          </p>
                          <p className="text-sm text-muted-foreground">
                            or click to browse
                          </p>
                        </div>
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

                  {/* Progress Bar */}
                  {uploading && (
                    <div className="mt-4">
                      <div className="flex justify-between text-sm mb-1">
                        <span>Uploading and extracting curriculum data...</span>
                        <span>{uploadProgress}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-primary h-2 rounded-full transition-all duration-300"
                          style={{ width: `${uploadProgress}%` }}
                        ></div>
                      </div>
                    </div>
                  )}

                  {error && (
                    <div className="mt-4 p-4 bg-destructive/10 border border-destructive/20 rounded-lg">
                      <p className="text-destructive text-sm">{error}</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Upload Button */}
              <div className="flex justify-between">
                <Link href="/dashboard">
                  <Button variant="outline">Cancel</Button>
                </Link>
                <Button
                  onClick={handleUpload}
                  disabled={!file || uploading}
                  size="lg"
                >
                  {uploading ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-2" />
                      Upload & Process
                    </>
                  )}
                </Button>
              </div>

              {/* Help */}
              <Card className="mt-8">
                <CardContent className="p-6">
                  <h3 className="font-semibold mb-2">What happens next?</h3>
                  <ol className="text-sm text-muted-foreground space-y-2 list-decimal list-inside">
                    <li>SchemeKnit extracts curriculum data from your document</li>
                    <li>You review and approve the extracted information</li>
                    <li>You configure lesson plan settings (duration, template, etc.)</li>
                    <li>SchemeKnit generates your lesson plans</li>
                    <li>You review, edit, and export your lesson plans</li>
                  </ol>
                  <p className="text-xs text-muted-foreground mt-4">
                    Supported formats: Word (.docx) and PDF. Maximum file size: 50 MB.
                  </p>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </main>
      <WhatsAppButton />
    </div>
  )
}
