export interface UploadResponse {
  dataset_id: string
  filename: string
  row_count: number
  columns: string[]
}

export interface DetectedColumns {
  entity_column: string | null
  category_column: string | null
  image_column: string | null
  timeline_start_column: string | null
  timeline_end_column: string | null
  value_columns: string[]
  timeline_format: string | null
}

export interface DatasetPreview {
  columns: string[]
  rows: Record<string, unknown>[]
}
