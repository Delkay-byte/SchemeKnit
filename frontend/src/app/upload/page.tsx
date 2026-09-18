'use client'

import { useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Upload, FileText, CheckCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { Header } from '@/components/header'
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

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      const validTypes = ['.docx']
      const fileExtension = '.' + selectedFile.name.split('.').pop()?.toLowerCase()
      if (!validTypes.includes(fileExtension)) {
        setError('Please select a .docx file')
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
      setFile(droppedFile)
      setError(null)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-4 py-8">
        <div className="max-w-2xl mx-auto">
          {/* Success State */}
          {success && result ? (
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
                </div>
                <div className="flex flex-col sm:flex-row gap-3 justify-center">
                  <Button size="lg" onClick={() => router.push(`/review/${result.scheme_id}`)}>
                    Review Curriculum
                    <span className="ml-2">→</span>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Upload Area */}
              <Card className="mb-6">
                <CardHeader>
                  <CardTitle>Upload Your Scheme of Work</CardTitle>
                  <CardDescription>
                    Upload a Word document (.docx) containing your scheme of work.
                    SchemeKnit will automatically extract the curriculum data.
                  </CardDescription>
                </CardHeader>
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
                          accept=".docx"
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
                    Supported format: Word (.docx). Maximum file size: 50 MB.
                  </p>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
