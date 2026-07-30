interface AssetUploadResponse {
  asset_id: string
  url: string
}

async function uploadAsset(path: string, file: File): Promise<AssetUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(path, { method: 'POST', body: formData })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `Upload failed: ${res.status}`)
  }
  return res.json()
}

export function uploadWatermark(file: File): Promise<AssetUploadResponse> {
  return uploadAsset('/api/assets/watermark', file)
}

export function uploadMusic(file: File): Promise<AssetUploadResponse> {
  return uploadAsset('/api/assets/music', file)
}
